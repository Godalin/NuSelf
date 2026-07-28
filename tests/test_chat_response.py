# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)

from nuself.agent.middleware import ToolOutcome
from nuself.agent.chat.response import (
    ConversationResponseSynthesizer,
    _LangChainChatSupervisor,
    _structured_output_from_state,  # pyright: ignore[reportPrivateUsage]
)
from nuself.agent.chat.thread import ThreadState
from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.llm import (
    LLMSettings,
    LangChainLLMEndpoint,
)


def _ignore_tool_outcome(_outcome: ToolOutcome) -> None:
    return None


def test_structured_output_state_is_authoritative() -> None:
    result = _structured_output_from_state(
        {
            "structured_response": ChatStructuredOutput(
                answer="Structured answer",
                evidence_references=["memory-1"],
                confidence=0.8,
                epistemic_status="grounded",
            ),
            "messages": [AIMessage(content="Different message")],
        }
    )

    assert result.answer == "Structured answer"
    assert result.evidence_references == ["memory-1"]


def test_invalid_structured_output_does_not_fall_back_to_message() -> None:
    with pytest.raises(ValueError, match="invalid structured_response: dict"):
        _structured_output_from_state(
            {
                "structured_response": {
                    "answer": "Dictionary compatibility",
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


def test_tool_protocol_text_is_rejected_in_every_state_path(
) -> None:
    with pytest.raises(ValueError, match="tool call text"):
        _structured_output_from_state(
            {
                "structured_response": ChatStructuredOutput(
                    answer="minimax:tool_call fake"
                ),
            }
        )


def test_endpoint_state_failure_retries_then_uses_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0

    def fail_endpoint(
        self: object,
        prompt: list[BaseMessage],
    ) -> None:
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise ValueError("invalid structured_response: NoneType")

    monkeypatch.setattr(
        "nuself.agent.chat.response._LangChainChatSupervisor.complete",
        fail_endpoint,
    )

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
        langchain_models=(endpoint,),
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    result = synthesizer.complete(
        [HumanMessage(content="hello")]
    )

    assert endpoint_calls == 2
    assert "LLM API is not configured yet" in result.answer
    assert result.answer.endswith("Last message: hello")


def test_protocol_failure_retries_same_endpoint_without_failover(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls: list[int] = []

    def fail_endpoint(
        self: _LangChainChatSupervisor,
        prompt: list[BaseMessage],
    ) -> None:
        del prompt
        endpoint_calls.append(self._endpoint.index)
        raise ValueError("invalid structured response")

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        fail_endpoint,
    )
    endpoints = tuple(
        LangChainLLMEndpoint(
            index=index,
            settings=LLMSettings(
                base_url=f"https://endpoint-{index}.invalid",
                api_key="test",
                model=f"model-{index}",
            ),
            model=cast(Any, object()),
        )
        for index in range(2)
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=endpoints,
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    result = synthesizer.complete(
        [HumanMessage(content="hello")]
    )

    assert endpoint_calls == [0, 0]
    assert result.answer.endswith("Last message: hello")


@pytest.mark.parametrize(
    "error",
    [
        AssertionError("broken chat invariant"),
        AttributeError("missing chat dependency"),
        TypeError("invalid internal chat call"),
    ],
    ids=["assertion", "attribute", "type"],
)
def test_pre_tool_implementation_errors_propagate_without_retry_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
) -> None:
    endpoint_calls = 0
    diagnostics: list[str] = []

    def fail_endpoint(
        self: _LangChainChatSupervisor,
        prompt: list[BaseMessage],
    ) -> None:
        del self, prompt
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise error

    def capture_diagnostic(
        failure: BaseException,
        **kwargs: object,
    ) -> None:
        del failure
        diagnostics.append(str(kwargs["event"]))

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        fail_endpoint,
    )
    monkeypatch.setattr(
        "nuself.agent.chat.response.report_observed_failure",
        capture_diagnostic,
    )
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
        langchain_models=(endpoint,),
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    with pytest.raises(type(error)) as caught:
        synthesizer.complete([HumanMessage(content="hello")])

    assert caught.value is error
    assert endpoint_calls == 1
    assert diagnostics == []


def test_availability_failure_uses_shared_endpoint_failover(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls: list[int] = []

    def invoke_endpoint(
        self: _LangChainChatSupervisor,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        del prompt
        endpoint_calls.append(self._endpoint.index)
        if self._endpoint.index == 0:
            raise RuntimeError("HTTP 429 rate limit")
        return ChatStructuredOutput(answer="backup response")

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        invoke_endpoint,
    )
    endpoints = tuple(
        LangChainLLMEndpoint(
            index=index,
            settings=LLMSettings(
                base_url=f"https://endpoint-{index}.invalid",
                api_key="test",
                model=f"model-{index}",
            ),
            model=cast(Any, object()),
        )
        for index in range(2)
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=endpoints,
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    result = synthesizer.complete(
        [HumanMessage(content="hello")]
    )

    assert endpoint_calls == [0, 1]
    assert result.answer == "backup response"


def test_tool_outcome_suppresses_retry_even_for_implementation_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0
    events: list[str] = []

    def fail_after_tool(
        self: object,
        prompt: list[BaseMessage],
    ) -> None:
        del self, prompt
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise AssertionError("implementation failed after tool execution")

    def report_failure(
        error: BaseException,
        **kwargs: object,
    ) -> None:
        del error
        events.append(str(kwargs["event"]))

    def has_tool_outcomes(self: object) -> bool:
        del self
        return True

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        fail_after_tool,
    )
    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "has_tool_outcomes",
        property(has_tool_outcomes),
    )
    monkeypatch.setattr(
        "nuself.agent.chat.response.report_observed_failure",
        report_failure,
    )

    endpoints = tuple(
        LangChainLLMEndpoint(
            index=index,
            settings=LLMSettings(
                base_url=f"https://endpoint-{index}.invalid",
                api_key="test",
                model=f"model-{index}",
            ),
            model=cast(Any, object()),
        )
        for index in range(2)
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=endpoints,
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    result = synthesizer.complete(
        [HumanMessage(content="mutate once")]
    )

    assert endpoint_calls == 1
    assert "LLM API is not configured yet" in result.answer
    assert result.answer.endswith("Last message: mutate once")
    assert events == ["llm_retry_suppressed_after_tool_call"]


def test_diagnostic_failure_preserves_retry_and_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0

    def fail_endpoint(
        self: object,
        prompt: list[BaseMessage],
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
        langchain_models=(endpoint,),
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )

    with pytest.warns(RuntimeWarning) as captured:
        result = synthesizer.complete(
            [HumanMessage(content="hello")]
        )

    assert endpoint_calls == 2
    assert "LLM API is not configured yet" in result.answer
    assert result.answer.endswith("Last message: hello")
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
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=(),
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
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
