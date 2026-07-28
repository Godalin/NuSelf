# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage

from nuself.agent.chat.response import (
    ConversationResponseSynthesizer,
    _plain_fallback_output,  # pyright: ignore[reportPrivateUsage]
    _structured_output_from_state,  # pyright: ignore[reportPrivateUsage]
)
from nuself.agent.chat.thread import ThreadState
from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.llm import (
    ChatMessage,
    LLMSettings,
    LangChainLLMEndpoint,
)


def test_structured_output_state_is_authoritative() -> None:
    result = _structured_output_from_state(
        {
            "structured_response": {
                "answer": "Structured answer",
                "evidence_references": ["memory-1"],
                "confidence": 0.8,
                "epistemic_status": "grounded",
            },
            "messages": [AIMessage(content="Different message")],
        }
    )

    assert result.answer == "Structured answer"
    assert result.evidence_references == ["memory-1"]


def test_invalid_structured_output_does_not_fall_back_to_message() -> None:
    with pytest.raises(ValueError, match="answer"):
        _structured_output_from_state(
            {
                "structured_response": {
                    "evidence_references": [],
                },
                "messages": [AIMessage(content="Plausible fallback")],
            }
        )


def test_invalid_structured_output_type_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="invalid structured_response: NoneType",
    ):
        _structured_output_from_state(
            {
                "structured_response": None,
                "messages": [AIMessage(content="Plausible fallback")],
            }
        )


def test_missing_structured_output_does_not_parse_message_state() -> None:
    with pytest.raises(
        ValueError,
        match="missing structured_response",
    ):
        _structured_output_from_state(
            {"messages": [AIMessage(content="Plausible fallback")]}
        )


def test_plain_fallback_preserves_non_protocol_text() -> None:
    raw = "{This is ordinary unfinished prose"

    result = _plain_fallback_output(raw)

    assert result.answer == raw
    assert result.evidence_references == []
    assert result.confidence is None
    assert result.epistemic_status == "inferred"


@pytest.mark.parametrize(
    "raw",
    (
        '{"answer":"A"}',
        '{"answer":"private draft"',
        "```json\n"
        '{"answer":"Fenced answer","epistemic_status":"uncertain"}\n'
        "```",
    ),
)
def test_plain_fallback_rejects_response_protocol_text(
    raw: str,
) -> None:
    with pytest.raises(ValueError, match="forbidden response protocol"):
        _plain_fallback_output(raw)


def test_plain_fallback_rejects_visible_tool_call(
) -> None:
    with pytest.raises(ValueError, match="visible tool call text"):
        _plain_fallback_output("minimax:tool_call private")


@pytest.mark.parametrize(
    "state",
    [
        {
            "structured_response": {
                "answer": "minimax:tool_call fake",
            },
        },
    ],
)
def test_tool_protocol_text_is_rejected_in_every_state_path(
    state: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="tool call text"):
        _structured_output_from_state(state)


def test_endpoint_state_failure_retries_then_uses_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0

    def fail_endpoint(
        self: object,
        prompt: list[ChatMessage],
    ) -> None:
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise ValueError("invalid structured_response: NoneType")

    monkeypatch.setattr(
        "nuself.agent.chat.response._LangChainChatSupervisor.complete",
        fail_endpoint,
    )

    class LocalLLM:
        calls = 0

        def complete(self, messages: list[ChatMessage]) -> str:
            self.calls += 1
            return "Local fallback"

    local_llm = LocalLLM()

    def ignore_tool_call(*args: object, **kwargs: object) -> None:
        return None

    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://example.invalid",
            api_key="test",
            model="test-model",
        ),
        model=cast(Any, object()),
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        llm=local_llm,
        langchain_models=(endpoint,),
        tools=(),
        log_tool_call=ignore_tool_call,
    )

    result = synthesizer.complete(
        [ChatMessage(role="user", content="hello")]
    )

    assert endpoint_calls == 2
    assert local_llm.calls == 1
    assert result.answer == "Local fallback"


def test_diagnostic_failure_preserves_retry_and_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0

    def fail_endpoint(
        self: object,
        prompt: list[ChatMessage],
    ) -> None:
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise ValueError("invalid endpoint response")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.agent.chat.response._LangChainChatSupervisor.complete",
        fail_endpoint,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    class LocalLLM:
        calls = 0

        def complete(self, messages: list[ChatMessage]) -> str:
            self.calls += 1
            return "Local fallback"

    local_llm = LocalLLM()
    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://example.invalid",
            api_key="test",
            model="test-model",
        ),
        model=cast(Any, object()),
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        llm=local_llm,
        langchain_models=(endpoint,),
        tools=(),
        log_tool_call=lambda *args, **kwargs: None,
    )

    with pytest.warns(RuntimeWarning) as captured:
        result = synthesizer.complete(
            [ChatMessage(role="user", content="hello")]
        )

    assert endpoint_calls == 2
    assert local_llm.calls == 1
    assert result.answer == "Local fallback"
    messages = [str(warning.message) for warning in captured]
    assert any("chat/llm_endpoint_retry" in message for message in messages)
    assert any(
        "chat/llm_endpoints_exhausted" in message
        for message in messages
    )


def test_finalize_log_failure_cannot_replace_accepted_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.agent.chat.response.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        llm=cast(Any, object()),
        langchain_models=(),
        tools=(),
        log_tool_call=lambda *args, **kwargs: None,
    )
    state = ConversationTurnState.start(
        ThreadState.empty("thread-1"),
        "hello",
        "thread-1",
    )
    draft = ChatStructuredOutput(answer="accepted response")

    with pytest.warns(
        RuntimeWarning,
        match=(
            "chat/final_response_log_failed: audit store unavailable; "
            "structured logging failed: audit store unavailable"
        ),
    ):
        result = synthesizer.finalize(state, draft)

    assert result is draft
