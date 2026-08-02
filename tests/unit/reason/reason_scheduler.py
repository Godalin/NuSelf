"""Tests for ReasonScheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nuself.config import runtime_paths
from nuself.log.reader import read_log_events
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonAdvancerProtocol
from reason_fixtures import ReasonScheduler
from reason_fixtures import ReasonService
from nuself.storage.authority import auto_backend
from tests.backend import owned_backend


def _reason_service(**kwargs: Any) -> ReasonService:
    return ReasonService(prompt_generator=_test_prompt_generator, **kwargs)


def _test_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."


def test_run_once_no_active_threads_does_nothing(tmp_path: Path) -> None:
    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=_null_advancer(),
        service=_reason_service(project_root=tmp_path),
        interval_seconds=600,
    )
    scheduler.run_once()


def test_run_once_skips_thread_on_cooldown(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test")
    cooldown_end = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    cooled = ReasoningThread(
        id=thread.id,
        topic=thread.topic,
        status=thread.status,
        working_summary=thread.working_summary,
        evidence_refs=list(thread.evidence_refs),
        priority=thread.priority,
        last_advanced_at=thread.last_advanced_at,
        next_review_after=thread.next_review_after,
        skip_next_advance_until=cooldown_end,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        active_items_data=thread.active_items_data,
        pending_items_data=thread.pending_items_data,
        next_steps_data=thread.next_steps_data,
        mandates_data=thread.mandates_data,
    )
    repo = ReasonRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    repo.save_thread(cooled)

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=_null_advancer(),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()


def test_run_once_never_advances_corrupt_cooldown_record(
    tmp_path: Path,
) -> None:
    backend = auto_backend(tmp_path / "private")
    thread = ReasoningThread(topic="Corrupt cooldown")
    wire = thread.to_wire()
    wire["skip_next_advance_until"] = "not-a-time"
    backend.collection("reason_threads").put(thread.id, wire)
    repository = ReasonRepository(
        runtime_paths(tmp_path),
        backend=backend,
    )
    service = _reason_service(
        project_root=tmp_path,
        repository=repository,
    )
    called = False

    class RecordingAdvancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            del thread
            nonlocal called
            called = True
            return None

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=RecordingAdvancer(),
        service=service,
        interval_seconds=600,
    )

    scheduler.run_once()

    assert not called
    event = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "reason_threads",
        "record_id": thread.id,
    }
    assert thread.topic not in str(event.to_record())
    with pytest.raises(ValueError):
        repository.get_thread(thread.id)


def test_run_once_advances_eligible_thread_when_audit_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(
        "nuself.reason.scheduler.REASON_AUDIT.write",
        drop_audit,
    )
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test advance")

    called = False

    class RecordingAdvancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            nonlocal called
            called = True
            return ReasoningStep(
                thread_id=thread.id,
                kind="progress",
                summary="Advanced",
                delta="Delta",
            )

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=RecordingAdvancer(),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()

    assert called
    steps = service.list_steps(thread.id)
    assert len(steps) == 1
    assert steps[0].summary == "Advanced"


def test_run_once_respects_cooldown_after_advance(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test cooldown")

    class Advancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            return ReasoningStep(
                thread_id=thread.id,
                kind="progress",
                summary="s",
                delta="d",
            )

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=Advancer(),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()

    updated = service.show_thread(thread.id)
    assert updated.skip_next_advance_until is not None
    cooldown = datetime.fromisoformat(updated.skip_next_advance_until)
    assert cooldown > datetime.now(UTC)


def test_run_once_logs_and_cools_down_failed_advance(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test failure")

    class FailingAdvancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            del thread
            raise FileNotFoundError("missing tmp")

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=FailingAdvancer(),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()

    updated = service.show_thread(thread.id)
    assert updated.skip_next_advance_until is not None
    cooldown = datetime.fromisoformat(updated.skip_next_advance_until)
    assert cooldown > datetime.now(UTC)
    assert service.list_steps(thread.id) == []

    events = read_log_events(project_root=tmp_path, component="reasoning")
    failed = [event for event in events if event.event == "scheduler_advance_failed"]
    assert len(failed) == 1
    assert failed[0].reason_id == thread.id
    assert failed[0].status == "error"
    assert failed[0].metadata == {}


def test_scheduler_failure_log_cannot_raise_or_undo_cooldown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test failure")

    class FailingAdvancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            del thread
            raise FileNotFoundError("missing tmp")

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
    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=FailingAdvancer(),
        service=service,
        interval_seconds=600,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = scheduler.run_once()

    assert result is None
    updated = service.show_thread(thread.id)
    assert updated.skip_next_advance_until is not None
    assert service.list_steps(thread.id) == []


def _null_advancer() -> ReasonAdvancerProtocol:
    class NullAdvancer:
        def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
            del thread
            return None
    return NullAdvancer()
