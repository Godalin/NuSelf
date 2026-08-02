from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nuself.config import runtime_paths
from tests.backend import owned_backend
from nuself.trace.model import ThoughtTrace, TraceLink
from nuself.trace.repository import TraceNotFound, TraceRepository
from nuself.trace.service import TraceRecorder


def _repository(root: Path) -> TraceRepository:
    return TraceRepository(
        runtime_paths(root),
        backend=owned_backend(root),
    )


def test_trace_repository_saves_lists_searches_and_links(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    recorder = TraceRecorder(repo)

    trace = recorder.record_chat_turn(
        title="Answer about memory time",
        summary="NuSelf answered using temporal memory context.",
        user_input="thread:default:1:user",
        assistant_output="thread:default:2:assistant",
        conversation_id="default",
        evidence_refs=["mem_123"],
        participants=["chat_agent", "memory"],
        decision_points=["Memory context included observed_at."],
    )
    link = repo.save_link(
        TraceLink(
            source_id=trace.id,
            target_id="mem_123",
            relation="cites",
            summary="The answer cited a memory entry.",
        )
    )

    traces = repo.list_traces()
    matches = repo.search_traces("temporal")
    links = repo.links_for(trace.id)

    assert traces == [trace]
    assert matches == [trace]
    assert links == [link]
    assert (
        owned_backend(tmp_path)
        .collection("trace_nodes")
        .get(trace.id)
        == trace.to_wire()
    )
    assert (
        owned_backend(tmp_path)
        .collection("trace_edges")
        .get(link.id)
        == link.to_wire()
    )


def test_trace_repository_finds_related_artifact_references(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    memory_trace = repo.save_trace(ThoughtTrace(
        kind="memory_update",
        title="Remembered preference",
        summary="Captured a durable preference.",
        outputs=["memory:mem_123"],
        metadata={
            "primary_artifact": "memory:mem_123",
            "nested": {"references": ["memory:mem_nested"]},
        },
    ))
    reason_trace = repo.save_trace(ThoughtTrace(
        kind="reason_step",
        title="Reason step",
        summary="Advanced with memory evidence.",
        inputs=["reason:abc"],
        evidence_refs=["memory:mem_123"],
        outputs=["reason:abc", "reason_step:step_1"],
    ))
    link = repo.save_link(
        TraceLink(
            source_id="memory:mem_123",
            target_id="reason:abc",
            relation="supports",
            summary="Memory supported the reason thread.",
        )
    )

    assert repo.traces_for_artifact("memory:mem_123") == [memory_trace, reason_trace]
    assert repo.traces_for_artifact("memory:mem_nested") == [memory_trace]
    assert repo.links_for_artifact("memory:mem_123") == [link]


def test_trace_repository_hides_internal_records_by_default(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    private = repo.save_trace(
        ThoughtTrace(kind="decision", title="Private decision", summary="Visible locally.")
    )
    internal = repo.save_trace(
        ThoughtTrace(kind="decision", title="Internal decision", summary="Hidden normally.", visibility="internal")
    )

    assert repo.list_traces() == [private]
    assert repo.list_traces(visibility="internal") == [internal]
    assert repo.list_traces(visibility="all") == [private, internal]


def test_trace_repository_resolves_numeric_handle(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    first = repo.save_trace(ThoughtTrace(kind="decision", title="First", summary="First trace."))
    second = repo.save_trace(ThoughtTrace(kind="decision", title="Second", summary="Second trace."))

    assert repo.resolve_trace("0") == first
    assert repo.resolve_trace("1") == second
    with pytest.raises(TraceNotFound):
        repo.resolve_trace("2")


def test_trace_repository_concurrent_saves(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    traces = tuple(
        ThoughtTrace(kind="decision", title=f"Trace {index}", summary=f"Summary {index}.")
        for index in range(16)
    )

    def save_trace(index: int) -> None:
        repo.save_trace(traces[index])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_trace, range(len(traces))))

    stored = repo.list_traces()
    assert {trace.id for trace in stored} == {trace.id for trace in traces}
