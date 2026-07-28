"""Tests for ReasonAdvancer."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any, cast

import pytest

from nuself.logs import read_log_events
from nuself.reason.advancer import (
    REASON_ADVANCE_SYSTEM_PROMPT,
    ReasonAdvancer,
    _current_reason_thread_id,
    build_advance_prompt,
    build_system_prompt,
    step_from_data,
)
from nuself.reason.domain import ReasoningThread
from nuself.runtime import RuntimeContext, current_runtime_context, runtime_context
from nuself.workspace import PrivateWorkspaceStore


class _RecordingAgent:
    def __init__(self) -> None:
        self.contexts: list[RuntimeContext] = []

    def invoke(self, _input: object) -> dict[str, object]:
        self.contexts.append(current_runtime_context())
        return {
            "structured_response": {
                "summary": "advanced",
                "delta": "changed",
                "kind": "progress",
                "output": "result",
            }
        }


class _FailingAgent:
    def invoke(self, _input: object) -> dict[str, object]:
        assert _current_reason_thread_id() == "reason-test"
        raise RuntimeError("agent failed")


def _advancer_with_agent(
    project_root: Path,
    agent: _RecordingAgent | _FailingAgent,
) -> ReasonAdvancer:
    advancer = ReasonAdvancer(project_root=project_root)
    dynamic = cast(Any, advancer)
    dynamic._agent = agent
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
            thread_id="reason-test",
            request_id="request-1",
            turn_id="turn-1",
            job_id="job-1",
            trace_id="trace-1",
            source="reason_scheduler",
        )
    ]
    assert current_runtime_context() == RuntimeContext()


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
    failure = next(event for event in events if event.event == "advance_tool_failed")
    assert failure.thread_id == "reason-test"
    assert failure.request_id == "request-1"
    assert failure.source == "client"


def test_workspace_tools_route_by_shared_reason_thread_context(
    tmp_path: Path,
) -> None:
    advancer = ReasonAdvancer(
        project_root=tmp_path,
        workspace_store=PrivateWorkspaceStore(tmp_path, scope="reason"),
    )
    tools = cast(Any, advancer)._build_workspace_tools()
    tool_map = {tool.name: tool for tool in tools}
    put = tool_map["workspace_put"]
    get = tool_map["workspace_get"]

    with runtime_context(thread_id="reason-a"):
        assert put.invoke({"key": "item", "value": '{"owner": "a"}'}) == (
            "Stored item"
        )
        assert '"owner": "a"' in get.invoke({"key": "item"})

    with runtime_context(thread_id="reason-b"):
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


def teststep_from_data_accepts_valid() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "terminal_status": "suggest_resolved",
        "terminal_reason": "done",
    }
    step = step_from_data(data, "test-thread")
    assert step is not None
    assert step.id is not None
    assert step.thread_id == "test-thread"
    assert step.summary == "s"
    assert step.delta == "d"
    assert step.kind == "progress"
    assert step.output == "out"
    assert step.terminal_status == "suggest_resolved"
    assert step.terminal_reason == "done"


def teststep_from_data_defaults_invalid_terminal_status_to_continue() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "terminal_status": "done",
    }

    step = step_from_data(data, "test-thread")

    assert step is not None
    assert step.terminal_status == "continue"


def teststep_from_data_filters_non_string_evidence_refs() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "evidence_refs": ["mem_1", 3, None],
    }
    step = step_from_data(data, "test-thread")

    assert step is not None
    assert step.evidence_refs == ["mem_1"]


def teststep_from_data_rejects_missing_fields() -> None:
    assert step_from_data({"kind": "progress"}, "t") is None  # type: ignore[reportArgumentType]
    assert step_from_data({"summary": "s", "delta": "d"}, "t") is None  # type: ignore[reportArgumentType]
    assert step_from_data({"summary": "s", "delta": "d", "kind": "progress"}, "t") is None  # type: ignore[reportArgumentType]


def teststep_from_data_rejects_invalid_kind() -> None:
    assert step_from_data({"summary": "s", "delta": "d", "kind": "invalid", "output": "out"}, "t") is None  # type: ignore[reportArgumentType]
