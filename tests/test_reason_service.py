"""Tests for reason service."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from nuself.logs import read_log_events
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def test_start_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("What should I do?")
    assert thread.question == "What should I do?"
    assert thread.status == "active"


def test_start_thread_writes_logs_under_project_root(tmp_path: Path) -> None:
    service = ReasonService(project_root=tmp_path)

    service.start_thread("Where should reason logs live?")

    events = read_log_events(project_root=tmp_path, component="reasoning")
    assert events
    assert events[-1].event == "thread_started"
    assert (tmp_path / "private" / "logs" / "reasoning.log").is_file()


def test_start_thread_initializes_private_workspace(tmp_path: Path) -> None:
    service = ReasonService(project_root=tmp_path)

    thread = service.start_thread("Where should scratch state live?")

    workspace = service.workspace_paths(thread.id)
    assert workspace.root == tmp_path / "private" / "workspaces" / "reason" / thread.id
    assert workspace.database.is_file()
    assert workspace.artifacts.is_dir()
    assert workspace.notes.is_dir()
    with sqlite3.connect(workspace.database) as conn:
        rows = dict(conn.execute("SELECT key, value FROM workspace_meta").fetchall())
    assert rows["scope"] == "reason"
    assert rows["owner_id"] == thread.id


def test_start_and_list(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    service.start_thread("Question 1")
    service.start_thread("Question 2")
    threads = service.list_threads()
    assert len(threads) == 2


def test_start_with_evidence(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test", evidence_refs=("ref-1", "ref-2"))
    assert thread.evidence_refs == ["ref-1", "ref-2"]


def test_show_thread_by_id(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    created = service.start_thread("Show me")
    shown = service.show_thread(created.id)
    assert shown.id == created.id


def test_pause_and_resume_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    paused = service.pause_thread(t.id)
    assert paused.status == "paused"
    resumed = service.resume_thread(t.id)
    assert resumed.status == "active"


def test_resolve_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    resolved = service.resolve_thread(t.id)
    assert resolved.status == "resolved"


def test_archive_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    archived = service.archive_thread(t.id)
    assert archived.status == "archived"


def test_invalid_transition_raises(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    service.resolve_thread(t.id)
    try:
        service.pause_thread(t.id)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_advance_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test advance")
    advanced = service.advance_thread(t.id)
    assert advanced.last_advanced_at is not None
    steps = service.list_steps(t.id)
    assert len(steps) == 1


def test_advance_paused_thread_raises(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    service.pause_thread(t.id)
    try:
        service.advance_thread(t.id)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_active_thread_cap(tmp_path: Path) -> None:
    from nuself.reason.service import MAX_ACTIVE_THREADS

    service = ReasonService(repository=ReasonRepository(tmp_path))
    for i in range(MAX_ACTIVE_THREADS):
        service.start_thread(f"Question {i}")
    try:
        service.start_thread("One too many")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "already" in str(exc)
