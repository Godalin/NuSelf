# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from nuself.agent.middleware import ToolOutcome
from nuself.agent.errors import AgentInvalidOutputError, AgentProtocolError
from nuself.agent.chat.response import (
    ConversationResponseSynthesizer,
    _LangChainChatSupervisor,
    _structured_output_from_state,  # pyright: ignore[reportPrivateUsage]
)
from nuself.conversation import ConversationState
from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.agent.endpoint import (
    LLMSettings,
    LangChainLLMEndpoint,
)
from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import (
    component,
    mutating,
    requires_confirmation,
    tool,
)
from nuself.runtime.context import runtime_context
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.messages import RuntimeEnvelope
from nuself.runtime.frontend import (
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequired,
    RequestApprovalPort,
    use_approval_grant,
)


def _ignore_tool_outcome(_outcome: ToolOutcome) -> None:
    return None


class _ToolCallingFakeChatModel(GenericFakeChatModel):
    def bind_tools(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return self


@pytest.mark.parametrize("approved", [True, False])
def test_synthesizer_resumes_exact_tool_call_without_regenerating_it(
    approved: bool,
) -> None:
    mutations: list[str] = []
    events = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    events.attach_projection(captured.append)

    @tool(name="memory_create", description="Create one memory.")
    @component("memory")
    @mutating
    @requires_confirmation(
        action="create",
        resource="memory",
        summary=lambda _args, kwargs: f"Create {kwargs['title']}",
    )
    def create_memory(title: str) -> str:
        mutations.append(title)
        return f"created {title}"

    framework_tool = materialize_tool(
        create_memory,
        executor=FeatureExecutor(
            approvals=RequestApprovalPort(),
            events=events,
        ),
    )
    model = _ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "memory_create",
                            "args": {"title": "exact"},
                            "id": "memory-call",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "ChatStructuredOutput",
                            "args": {
                                "answer": "done",
                                "evidence_references": [],
                                "confidence": 1.0,
                                "epistemic_status": "grounded",
                            },
                            "id": "response-call",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        )
    )
    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://example.invalid",
            api_key="test",
            model="test-model",
        ),
        model=model,
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=None,
        langchain_models=(endpoint,),
        tools=(framework_tool,),
        log_tool_outcome=_ignore_tool_outcome,
        report_tool_log_failure=None,
    )
    prompt: list[BaseMessage] = [HumanMessage(content="remember this")]

    with runtime_context(
        conversation_id="default",
        turn_id="turn-checkpoint",
    ):
        with pytest.raises(ApprovalRequired) as paused:
            synthesizer.complete(prompt)
        request = paused.value.request
        decision = (
            ApprovalDecision(
                True,
                approver="tester",
                input_kind="affirmative",
            )
            if approved
            else ApprovalDecision(False, input_kind="declined")
        )
        with use_approval_grant(ApprovalGrant(request, decision)):
            result = synthesizer.complete(prompt)

    assert result.answer == "done"
    assert mutations == (["exact"] if approved else [])
    payloads = [
        RuntimeLogEventPayload.from_mapping(event.payload)
        for event in captured
    ]
    assert [
        payload.metadata["frontend_event"]
        for payload in payloads
        if payload.metadata is not None
        and "frontend_event" in payload.metadata
    ] == ["approval_requested", "approval_decided"]


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
    with pytest.raises(
        AgentInvalidOutputError,
        match="invalid structured_response: dict",
    ):
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
        AgentInvalidOutputError,
        match="invalid structured_response: NoneType",
    ):
        _structured_output_from_state(
            {
                "structured_response": None,
                "messages": [AIMessage(content="Plausible fallback")],
            }
        )


def test_missing_structured_output_preserves_final_framework_message() -> None:
    result = _structured_output_from_state(
        {"messages": [AIMessage(content="Plausible framework answer")]}
    )

    assert result.answer == "Plausible framework answer"
    assert result.evidence_references == []
    assert result.confidence is None
    assert result.epistemic_status == "inferred"


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content=""),
        AIMessage(
            content="pending",
            tool_calls=[
                {
                    "name": "memory_search",
                    "args": {},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
    ],
)
def test_missing_structured_output_rejects_non_final_message(
    message: AIMessage,
) -> None:
    with pytest.raises(
        AgentProtocolError,
        match="missing structured_response",
    ):
        _structured_output_from_state({"messages": [message]})


def test_tool_protocol_text_is_rejected_in_every_state_path(
) -> None:
    with pytest.raises(AgentInvalidOutputError, match="tool call text"):
        _structured_output_from_state(
            {
                "structured_response": ChatStructuredOutput(
                    answer="minimax:tool_call fake"
                ),
            }
        )


def test_endpoint_state_failure_retries_then_reports_configured_failure(
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
    assert "configured LLM request failed" in result.answer
    assert "LLM API is not configured yet" not in result.answer
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
    assert "configured LLM request failed" in result.answer
    assert result.answer.endswith("Last message: hello")


@pytest.mark.parametrize(
    "error",
    [
        AssertionError("broken chat invariant"),
        AttributeError("missing chat dependency"),
        KeyError("missing chat registry entry"),
        NotImplementedError("chat path is not implemented"),
        TypeError("invalid internal chat call"),
    ],
    ids=["assertion", "attribute", "lookup", "not-implemented", "type"],
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
        "nuself.agent.chat.response.CHAT_AUDIT.failure",
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
            error = RuntimeError("provider failure")
            error.status_code = 429  # type: ignore[attr-defined]
            raise error
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

    assert endpoint_calls == [0, 0, 1]
    assert result.answer == "backup response"


@pytest.mark.parametrize(
    ("error", "uses_fallback"),
    [
        (RuntimeError("provider failed after tool execution"), True),
        (AssertionError("implementation failed after tool execution"), False),
    ],
    ids=["recoverable", "implementation"],
)
def test_tool_outcome_suppresses_retry_before_failure_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
    uses_fallback: bool,
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
        raise error

    def report_failure(
        error: BaseException,
        **kwargs: object,
    ) -> None:
        del error
        events.append(str(kwargs["event"]))

    def has_mutating_tool_outcomes(self: object) -> bool:
        del self
        return True

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        fail_after_tool,
    )
    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "has_mutating_tool_outcomes",
        property(has_mutating_tool_outcomes),
    )
    monkeypatch.setattr(
        "nuself.agent.chat.response.CHAT_AUDIT.failure",
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

    if uses_fallback:
        result = synthesizer.complete(
            [HumanMessage(content="mutate once")]
        )
        assert "configured LLM request failed" in result.answer
        assert "LLM API is not configured yet" not in result.answer
        assert result.answer.endswith("Last message: mutate once")
    else:
        with pytest.raises(type(error)) as caught:
            synthesizer.complete(
                [HumanMessage(content="mutate once")]
            )
        assert caught.value is error

    assert endpoint_calls == 1
    assert events == ["llm_retry_suppressed_after_tool_call"]


def test_readonly_tool_outcome_allows_transient_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0

    def complete_after_read(
        self: _LangChainChatSupervisor,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        del self, prompt
        nonlocal endpoint_calls
        endpoint_calls += 1
        if endpoint_calls == 1:
            error = RuntimeError("temporary provider failure")
            error.status_code = 503  # type: ignore[attr-defined]
            raise error
        return ChatStructuredOutput(answer="recovered")

    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "complete",
        complete_after_read,
    )
    monkeypatch.setattr(
        _LangChainChatSupervisor,
        "has_mutating_tool_outcomes",
        property(lambda self: False),
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

    result = synthesizer.complete([HumanMessage(content="remember")])

    assert endpoint_calls == 2
    assert result.answer == "recovered"


def test_diagnostic_failure_preserves_retry_and_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    endpoint_calls = 0
    provider_secret = "provider-secret-value"

    def fail_endpoint(
        self: object,
        prompt: list[BaseMessage],
    ) -> None:
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise ValueError(
            f"invalid endpoint response api_key={provider_secret}"
        )

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
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
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
    assert "configured LLM request failed" in result.answer
    assert "LLM API is not configured yet" not in result.answer
    assert result.answer.endswith("Last message: hello")
    messages = [str(warning.message) for warning in captured]
    assert provider_secret not in "\n".join(messages)
    assert "api_key=***" in "\n".join(messages)
    assert any(
        "component=chat event=llm_endpoint_retry" in message
        for message in messages
    )
    assert any(
        "component=chat event=llm_endpoints_exhausted" in message
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
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=(),
        tools=(),
        log_tool_outcome=_ignore_tool_outcome,
    )
    state = ConversationTurnState.start(
        ConversationState.empty("thread-1"),
        "hello",
        "thread-1",
    )
    draft = ChatStructuredOutput(answer="accepted response")

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = synthesizer.finalize(state, draft)

    assert result is draft
