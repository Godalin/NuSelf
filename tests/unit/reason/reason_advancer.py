"""Tests for ReasonAdvancer."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
import time
from typing import Any, cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from nuself.agent.middleware import ToolOutcome
from nuself.application.composition import compose_application
from nuself.reason.composition import compose_reason_advancer
from nuself.config.settings import runtime_paths
from nuself.agent.endpoint import LLMSettings, LangChainLLMEndpoint
from nuself.log.reader import read_log_events
from nuself.reason.advancer import (
    REASON_ADVANCE_SYSTEM_PROMPT,
    ReasonAdvancer,
    ReasonStepOutput,
    TrackedItemOutput,
    _current_reason_thread_id,
    build_advance_prompt,
    build_system_prompt,
    default_reason_advancer,
)
from nuself.reason.model import ReasoningThread
from nuself.reason.errors import ReasonAdvanceError
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.storage.authority import _create_sqlite_backend
from tests.backend import owned_backend


def _advancer_dependencies(project_root: Path) -> dict[str, Any]:
    application = compose_application(
        runtime_paths(project_root),
        owned_backend(project_root),
    )
    return {
        "paths": application.paths,
        "reason_service": application.reason.service,
        "persona_repository": application.personas,
        "trace_recorder": application.trace.recorder,
    }


def test_application_reason_composition_resolves_models_from_graph_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = compose_application(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    )
    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://reason.test/v1",
            api_key="test",
            model="reason-test",
        ),
        model=cast(BaseChatModel, object()),
    )
    captured: list[tuple[Path | None, object]] = []

    def configured(
        project_root: Path | None,
        *,
        config: object,
    ) -> tuple[LangChainLLMEndpoint, ...]:
        captured.append((project_root, config))
        return (endpoint,)

    monkeypatch.setattr(
        "nuself.reason.composition.configured_langchain_chat_models",
        configured,
    )

    advancer = compose_reason_advancer(
        application.paths,
        application.reason.service,
        application.personas,
        application.trace.recorder,
        application.config,
    )

    assert captured == [(tmp_path, application.config)]
    assert advancer._langchain_models == (endpoint,)


def test_default_reason_advancer_uses_explicit_endpoints_and_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://reason.test/v1",
            api_key="test",
            model="reason-test",
        ),
        model=cast(BaseChatModel, object()),
    )
    def create_agent(**kwargs: object) -> object:
        return kwargs

    def lookup(query: str) -> str:
        """Look up test context."""
        return query

    readonly_tool = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        lookup,
        name="test_lookup",
        metadata={"service_component": "memory"},
    )
    invalid_metadata_tool = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        lookup,
        name="invalid_metadata",
        metadata={"service_component": 3},
    )

    monkeypatch.setattr(
        "nuself.reason.advancer._create_agent",
        create_agent,
    )

    advancer = default_reason_advancer(
        **_advancer_dependencies(tmp_path),
        readonly_tools=(readonly_tool, invalid_metadata_tool),
        langchain_models=(endpoint,),
    )

    assert advancer._langchain_models == (endpoint,)
    assert advancer._reason_service is not None
    assert advancer._readonly_tools == (
        readonly_tool,
        invalid_metadata_tool,
    )
    assert advancer._tool_service_map["test_lookup"] == "memory"
    assert "invalid_metadata" not in advancer._tool_service_map


def test_default_reason_advancer_preserves_explicit_empty_endpoints(
    tmp_path: Path,
) -> None:
    advancer = default_reason_advancer(
        **_advancer_dependencies(tmp_path),
        langchain_models=(),
    )

    assert advancer._langchain_models == ()


class _RecordingAgent:
    def __init__(self) -> None:
        self.contexts: list[RuntimeContext] = []

    def invoke(self, _input: object) -> dict[str, object]:
        self.contexts.append(current_runtime_context())
        return {
            "structured_response": ReasonStepOutput(
                summary="advanced",
                delta="changed",
                kind="progress",
                output="result",
            )
        }


class _FailingAgent:
    def invoke(self, _input: object) -> dict[str, object]:
        assert _current_reason_thread_id() == "reason-test"
        raise RuntimeError("agent failed")


class _ConcurrentCaptureAgent:
    def __init__(self) -> None:
        self.advancer: ReasonAdvancer | None = None
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def invoke(self, _input: object) -> dict[str, object]:
        thread_id = _current_reason_thread_id()
        advancer = self.advancer
        assert advancer is not None
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            captured = cast(
                list[ToolOutcome],
                cast(Any, advancer)._captured,
            )
            captured.append(
                ToolOutcome(
                    f"tool-{thread_id}",
                    {"thread_id": thread_id},
                    result=thread_id,
                )
            )
            time.sleep(0.03)
            return {
                "structured_response": ReasonStepOutput(
                    summary=f"advanced {thread_id}",
                    delta="changed",
                    kind="progress",
                    output="result",
                )
            }
        finally:
            with self._lock:
                self._active -= 1


class _FailOnceAgent:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, _input: object) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("first call failed")
        return {
            "structured_response": ReasonStepOutput(
                summary="recovered",
                delta="changed",
                kind="progress",
                output="result",
            )
        }


def _advancer_with_agent(
    project_root: Path,
    agent: Any,
) -> ReasonAdvancer:
    advancer = ReasonAdvancer(
        **_advancer_dependencies(project_root),
        feature_executor=FeatureExecutor(),
    )
    dynamic = cast(Any, advancer)
    endpoint = LangChainLLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="https://reason.test/v1",
            api_key="test",
            model="reason-test",
        ),
        model=cast(BaseChatModel, object()),
    )
    dynamic._agents = ((endpoint, agent),)
    dynamic._tool_service_map = {}
    return advancer


def _advancer_with_agents(
    project_root: Path,
    agents: tuple[Any, ...],
) -> ReasonAdvancer:
    advancer = ReasonAdvancer(
        **_advancer_dependencies(project_root),
        feature_executor=FeatureExecutor(),
    )
    dynamic = cast(Any, advancer)
    dynamic._agents = tuple(
        (
            LangChainLLMEndpoint(
                index=index,
                settings=LLMSettings(
                    base_url=f"https://reason-{index}.test/v1",
                    api_key="test",
                    model=f"reason-{index}",
                ),
                model=cast(BaseChatModel, object()),
            ),
            agent,
        )
        for index, agent in enumerate(agents)
    )
    dynamic._tool_service_map = {}
    return advancer


def test_build_prompt_includes_thread_fields() -> None:
    thread = ReasoningThread(
        topic="Test question",
        working_summary="Some summary",
        evidence_refs=["ref1"],
        active_items_data=({"label": "hyp1", "kind": "finding"},),
        pending_items_data=({"label": "q1", "kind": "pending"},),
    )
    prompt = build_advance_prompt(thread)
    assert "Test question" in prompt
    assert "Some summary" in prompt
    assert "hyp1" in prompt
    assert "q1" in prompt
    assert "ref1" in prompt
    assert "at most one complete round" in prompt


def test_advance_uses_shared_reason_thread_context_and_restores_caller(
    tmp_path: Path,
) -> None:
    agent = _RecordingAgent()
    advancer = _advancer_with_agent(tmp_path, agent)
    thread = ReasoningThread(id="reason-test", topic="Q")

    with runtime_context(
        request_id="request-1",
        turn_id="turn-1",
        job_id="job-1",
        trace_id="trace-1",
        source="reason_scheduler",
    ):
        step = advancer.advance(thread)
        assert current_runtime_context() == RuntimeContext(
            request_id="request-1",
            turn_id="turn-1",
            job_id="job-1",
            trace_id="trace-1",
            source="reason_scheduler",
        )

    assert step is not None
    assert agent.contexts == [
        RuntimeContext(
            reason_id="reason-test",
            request_id="request-1",
            turn_id="turn-1",
            job_id="job-1",
            trace_id="trace-1",
            source="reason_scheduler",
        )
    ]
    assert current_runtime_context() == RuntimeContext()


def test_reason_advancer_fails_over_before_tool_execution(
    tmp_path: Path,
) -> None:
    class UnavailableAgent:
        calls = 0

        def invoke(self, _input: object) -> dict[str, object]:
            self.calls += 1
            error = RuntimeError("provider failure")
            error.status_code = 429  # type: ignore[attr-defined]
            raise error

    primary = UnavailableAgent()
    secondary = _RecordingAgent()
    advancer = _advancer_with_agents(
        tmp_path,
        (primary, secondary),
    )

    step = advancer.advance(
        ReasoningThread(id="reason-test", topic="Q")
    )

    assert step is not None
    assert step.summary == "advanced"
    assert primary.calls == 1
    assert len(secondary.contexts) == 1
    events = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )
    assert any(
        event.event == "llm_endpoint_failed_over"
        for event in events
    )


def test_reason_advancer_does_not_fail_over_protocol_error(
    tmp_path: Path,
) -> None:
    class ProtocolFailureAgent:
        calls = 0

        def invoke(self, _input: object) -> dict[str, object]:
            self.calls += 1
            raise ValueError("invalid structured response")

    primary = ProtocolFailureAgent()
    secondary = _RecordingAgent()
    advancer = _advancer_with_agents(
        tmp_path,
        (primary, secondary),
    )

    with pytest.raises(
        ValueError,
        match="invalid structured response",
    ):
        advancer.advance(
            ReasoningThread(id="reason-test", topic="Q")
        )

    assert primary.calls == 1
    assert secondary.contexts == []


def test_advance_rejects_dictionary_structured_response(
    tmp_path: Path,
) -> None:
    class DictionaryAgent:
        def invoke(self, _input: object) -> dict[str, object]:
            return {
                "structured_response": {
                    "summary": "manual protocol",
                    "delta": "invalid",
                    "kind": "progress",
                    "output": "must not be reparsed",
                }
            }

    advancer = _advancer_with_agent(tmp_path, DictionaryAgent())

    with pytest.raises(
        ReasonAdvanceError,
        match="did not return ReasonStepOutput",
    ):
        advancer.advance(ReasoningThread(id="reason-test", topic="Q"))


def test_advance_failure_logs_shared_context_and_restores_caller(
    tmp_path: Path,
) -> None:
    advancer = _advancer_with_agent(tmp_path, _FailingAgent())
    thread = ReasoningThread(id="reason-test", topic="Q")

    with runtime_context(request_id="request-1", source="client"):
        with pytest.raises(RuntimeError, match="agent failed"):
            advancer.advance(thread)
        assert current_runtime_context() == RuntimeContext(
            request_id="request-1",
            source="client",
        )

    events = read_log_events(project_root=tmp_path, component="reasoning")
    failure = next(event for event in events if event.event == "advance_failed")
    assert failure.reason_id == "reason-test"
    assert failure.request_id == "request-1"
    assert failure.source == "client"
    assert failure.error == "agent failed"
    assert "Traceback" not in failure.message


def test_agent_failure_still_projects_prior_failed_tool_outcome(
    tmp_path: Path,
) -> None:
    class FailingAfterToolAgent:
        def __init__(self) -> None:
            self.advancer: ReasonAdvancer | None = None

        def invoke(self, _input: object) -> dict[str, object]:
            assert self.advancer is not None
            captured = cast(
                list[ToolOutcome],
                cast(Any, self.advancer)._captured,
            )
            captured.append(
                ToolOutcome(
                    "workspace_put",
                    {"key": "decision"},
                    error="storage unavailable",
                )
            )
            raise RuntimeError("agent failed after tool")

    agent = FailingAfterToolAgent()
    advancer = _advancer_with_agent(tmp_path, agent)
    agent.advancer = advancer

    with pytest.raises(
        ReasonAdvanceError,
        match="failover suppressed after tool execution",
    ) as caught:
        advancer.advance(
            ReasoningThread(id="reason-test", topic="Q")
        )
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "agent failed after tool"

    events = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )
    tool_event = next(
        event
        for event in events
        if event.event == "service_tool_called"
    )
    assert tool_event.status == "failed"
    assert tool_event.metadata is not None
    assert tool_event.metadata["tool"] == "workspace_put"
    assert tool_event.metadata["error"] == "storage unavailable"
    assert any(
        event.event == "llm_failover_suppressed_after_tool_call"
        for event in events
    )
    assert events[-1].event == "advance_failed"
    assert events[-1].error == (
        "Reason endpoint failover suppressed after tool execution "
        "<- agent failed after tool"
    )


def test_advance_failure_log_cannot_mask_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    primary_error = RuntimeError("agent failed")

    class FailingAgent:
        def invoke(self, _input: object) -> dict[str, object]:
            raise primary_error

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
    advancer = _advancer_with_agent(tmp_path, FailingAgent())
    thread = ReasoningThread(id="reason-test", topic="Q")

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ), pytest.raises(RuntimeError) as captured:
        advancer.advance(thread)

    assert captured.value is primary_error
    assert current_runtime_context() == RuntimeContext()


def test_concurrent_advances_isolate_invocation_tool_capture(
    tmp_path: Path,
) -> None:
    agent = _ConcurrentCaptureAgent()
    advancer = _advancer_with_agent(tmp_path, agent)
    agent.advancer = advancer
    threads = (
        ReasoningThread(id="reason-a", topic="A"),
        ReasoningThread(id="reason-b", topic="B"),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        steps = tuple(executor.map(advancer.advance, threads))

    assert agent.max_active == 1
    for thread, step in zip(threads, steps, strict=True):
        assert step is not None
        assert len(step.tool_logs) == 1
        metadata = step.tool_logs[0]["metadata"]
        assert isinstance(metadata, Mapping)
        assert metadata["tool"] == f"tool-{thread.id}"
        assert metadata["result"] == thread.id


def test_advance_failure_releases_invocation_owner(
    tmp_path: Path,
) -> None:
    agent = _FailOnceAgent()
    advancer = _advancer_with_agent(tmp_path, agent)

    with pytest.raises(RuntimeError, match="first call failed"):
        advancer.advance(ReasoningThread(id="reason-first", topic="First"))

    step = advancer.advance(
        ReasoningThread(id="reason-second", topic="Second")
    )

    assert step is not None
    assert step.summary == "recovered"


def test_workspace_tools_route_by_shared_reason_thread_context(
    tmp_path: Path,
) -> None:
    _create_sqlite_backend(db_path=tmp_path / "nuself.sqlite").close()
    advancer = ReasonAdvancer(
        **_advancer_dependencies(tmp_path),
        feature_executor=FeatureExecutor(),
    )
    tools = cast(Any, advancer)._build_workspace_tools()
    tool_map = {tool.name: tool for tool in tools}
    put = tool_map["workspace_put"]
    get = tool_map["workspace_get"]

    with runtime_context(reason_id="reason-a"):
        assert put.invoke({"key": "item", "value": '{"owner": "a"}'}) == (
            "Stored item"
        )
        assert '"owner": "a"' in get.invoke({"key": "item"})

    with runtime_context(reason_id="reason-b"):
        assert get.invoke({"key": "item"}) == "Key item not found"

    with pytest.raises(
        RuntimeError,
        match="reason tool requires an active reason thread context",
    ):
        get.invoke({"key": "item"})


def test_build_prompt_empty_lists_omitted() -> None:
    thread = ReasoningThread(topic="Q")
    prompt = build_advance_prompt(thread)
    assert "Active items:" not in prompt
    assert "Pending items:" not in prompt
    assert "Evidence references:" not in prompt


def test_build_system_prompt_keeps_invariant_contract_with_generated_prompt() -> None:
    thread = ReasoningThread(topic="Q", reasoning_prompt="Move one debate turn at a time.")

    prompt = build_system_prompt(thread)

    assert REASON_ADVANCE_SYSTEM_PROMPT in prompt
    assert "Move one debate turn at a time." in prompt
    assert "ReasonStepOutput" in prompt
    assert "at most one complete round" in prompt
    assert "call persona_think for that persona" in prompt
    assert "do not fabricate later persona speech" in prompt
    assert "terminal_status=suggest_resolved" in prompt
    assert "Do not rely on prose alone to signal completion" in prompt


def test_reason_step_output_converts_typed_response() -> None:
    response = ReasonStepOutput(
        summary=" s ",
        delta=" d ",
        kind="progress",
        output="out",
        evidence_refs=["mem_1"],
        confidence=0.75,
        new_findings=[
            TrackedItemOutput(
                label="Finding",
                kind="finding",
            )
        ],
        terminal_status="suggest_resolved",
        terminal_reason=" done ",
    )

    step = response.to_step("test-thread")

    assert step.id is not None
    assert step.thread_id == "test-thread"
    assert step.summary == "s"
    assert step.delta == "d"
    assert step.kind == "progress"
    assert step.output == "out"
    assert step.evidence_refs == ("mem_1",)
    assert step.confidence == 0.75
    assert step.new_findings[0].label == "Finding"
    assert step.new_findings[0].status == "active"
    assert step.terminal_status == "suggest_resolved"
    assert step.terminal_reason == "done"


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "invalid"},
        {"terminal_status": "done"},
        {"confidence": 1.1},
        {"confidence": True},
        {"evidence_refs": ["mem_1", 3]},
        {"new_findings": [{"label": 3}]},
        {"unexpected": "field"},
    ],
)
def test_reason_step_output_rejects_invalid_protocol(
    overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
    }
    payload.update(overrides)

    with pytest.raises(ValidationError):
        ReasonStepOutput.model_validate(payload)
