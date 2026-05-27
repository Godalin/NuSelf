"""Tests for reason service."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from nuself.logs import read_log_events
from nuself.reason.domain import ReasoningStep
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.trace.service import TraceQueryService


def _reason_service(**kwargs: Any) -> ReasonService:
    return ReasonService(prompt_generator=_test_prompt_generator, **kwargs)


def _test_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."


def test_start_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("What should I do?")
    assert thread.topic == "What should I do?"
    assert thread.status == "active"


def test_start_thread_writes_logs_under_project_root(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    service.start_thread("Where should reason logs live?")

    events = read_log_events(project_root=tmp_path, component="reasoning")
    assert events
    assert events[-1].event == "thread_started"
    assert (tmp_path / "private" / "logs" / "reasoning.log").is_file()


def test_start_thread_initializes_private_workspace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("Where should scratch state live?")

    workspace = service.workspace_paths(thread.id)
    assert workspace.root == tmp_path / "private" / "workspaces" / "reason" / thread.id
    assert workspace.database.is_file()
    assert workspace.artifacts.is_dir()
    assert workspace.notes.is_dir()
    conn = sqlite3.connect(workspace.database)
    rows = dict(conn.execute("SELECT key, value FROM workspace_meta").fetchall())
    conn.close()
    assert rows["scope"] == "reason"
    assert rows["owner_id"] == thread.id


def test_start_and_list(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    service.start_thread("Question 1")
    service.start_thread("Question 2")
    threads = service.list_threads()
    assert len(threads) == 2


def test_start_with_evidence(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test", evidence_refs=("ref-1", "ref-2"))
    assert thread.evidence_refs == ["ref-1", "ref-2"]


def test_start_thread_records_trace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("What should be traced?", evidence_refs=("memory:abc",))

    traces = TraceQueryService(tmp_path).list_traces(kind="reason_thread")
    assert len(traces) == 1
    assert traces[0].outputs == [f"reason:{thread.id}"]
    assert traces[0].evidence_refs == ["memory:abc"]


def test_start_thread_records_trace_when_repository_is_injected(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path, repository=ReasonRepository(tmp_path))

    thread = service.start_thread("Injected repository should still trace")

    traces = TraceQueryService(tmp_path).list_traces(kind="reason_thread")
    assert len(traces) == 1
    assert traces[0].outputs == [f"reason:{thread.id}"]


def test_show_thread_by_id(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    created = service.start_thread("Show me")
    shown = service.show_thread(created.id)
    assert shown.id == created.id


def test_pause_and_resume_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    paused = service.pause_thread(t.id)
    assert paused.status == "paused"
    resumed = service.resume_thread(t.id)
    assert resumed.status == "active"


def test_resolve_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    resolved = service.resolve_thread(t.id)
    assert resolved.status == "resolved"


def test_archive_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    archived = service.archive_thread(t.id)
    assert archived.status == "archived"


def test_invalid_transition_raises(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    service.resolve_thread(t.id)
    try:
        service.pause_thread(t.id)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_advance_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test advance")
    step = _test_step(t.id)
    advanced = service.advance_thread(t.id, step=step)
    assert advanced.last_advanced_at is not None
    steps = service.list_steps(t.id)
    assert len(steps) == 1
    assert steps[0] == step


def test_advance_thread_records_trace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Trace advances")
    step = _test_step(thread.id)

    advanced = service.advance_thread(thread.id, step=step)

    steps = service.list_steps(thread.id)
    traces = TraceQueryService(tmp_path).list_traces(kind="reason_step")
    assert len(traces) == 1
    assert traces[0].outputs == [f"reason:{advanced.id}", f"reason_step:{steps[0].id}"]
    assert traces[0].metadata["step_kind"] == "progress"


def test_reason_step_rejects_non_object_tool_logs() -> None:
    try:
        ReasoningStep.from_wire(
            {
                "id": "step-test",
                "thread_id": "reason-test",
                "kind": "progress",
                "summary": "Advanced",
                "delta": "Moved",
                "tool_logs": ["not an object"],
                "created_at": "2026-05-27T00:00:00+00:00",
            }
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "tool_logs" in str(exc)


def test_advance_without_advancer_or_step_raises(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("No fallback advance")

    try:
        service.advance_thread(thread.id)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "no reason advancer configured" in str(exc)


def test_advance_when_advancer_returns_none_raises(tmp_path: Path) -> None:
    class EmptyAdvancer:
        def advance(self, thread: object) -> None:
            return None

    service = _reason_service(repository=ReasonRepository(tmp_path), advancer=EmptyAdvancer())
    thread = service.start_thread("No fake steps")

    try:
        service.advance_thread(thread.id)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "did not produce a structured step" in str(exc)


def test_advance_paused_thread_raises(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    service.pause_thread(t.id)
    try:
        service.advance_thread(t.id)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def _test_step(thread_id: str) -> ReasoningStep:
    return ReasoningStep(
        thread_id=thread_id,
        kind="progress",
        summary="Advanced",
        delta="Moved forward",
        output="Observable output",
    )


def test_active_thread_cap(tmp_path: Path) -> None:
    from nuself.reason.service import MAX_ACTIVE_THREADS

    service = _reason_service(repository=ReasonRepository(tmp_path))
    for i in range(MAX_ACTIVE_THREADS):
        service.start_thread(f"Question {i}")
    try:
        service.start_thread("One too many")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "already" in str(exc)
