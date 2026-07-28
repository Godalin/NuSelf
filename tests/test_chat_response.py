from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage

from nuself.agent.chat.response import (
    ConversationResponseSynthesizer,
    _structured_output_from_state,  # pyright: ignore[reportPrivateUsage]
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


def test_missing_structured_output_uses_compatibility_message() -> None:
    result = _structured_output_from_state(
        {"messages": [AIMessage(content="Compatibility answer")]}
    )

    assert result.answer == "Compatibility answer"


@pytest.mark.parametrize(
    "state",
    [
        {
            "structured_response": {
                "answer": "minimax:tool_call fake",
            },
        },
        {
            "messages": [
                AIMessage(content="minimax:tool_call fake"),
            ],
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
            return '{"answer":"Local fallback"}'

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
