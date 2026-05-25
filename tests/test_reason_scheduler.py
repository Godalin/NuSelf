"""Tests for ReasonScheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from nuself.reason.advancer import ReasonAdvancer
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.repository import ReasonRepository
from nuself.reason.scheduler import ReasonScheduler
from nuself.reason.service import ReasonService


def test_run_once_no_active_threads_does_nothing(tmp_path: Path) -> None:
    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=_null_advancer(),
        service=ReasonService(repository=ReasonRepository(tmp_path)),
        interval_seconds=600,
    )
    scheduler.run_once()


def test_run_once_skips_thread_on_cooldown(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test")
    cooldown_end = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    cooled = ReasoningThread(
        id=thread.id,
        topic=thread.topic,
        status=thread.status,
        working_summary=thread.working_summary,
        hypotheses=list(thread.hypotheses),
        open_questions=list(thread.open_questions),
        evidence_refs=list(thread.evidence_refs),
        priority=thread.priority,
        last_advanced_at=thread.last_advanced_at,
        next_review_after=thread.next_review_after,
        skip_next_advance_until=cooldown_end,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )
    repo = ReasonRepository(tmp_path)
    repo.save_thread(cooled)

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=_null_advancer(),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()


def test_run_once_advances_eligible_thread(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test advance")

    called = False

    class RecordingAdvancer:
        def advance(self, t: ReasoningThread) -> ReasoningStep | None:
            nonlocal called
            called = True
            return ReasoningStep(
                thread_id=t.id,
                kind="progress",
                summary="Advanced",
                delta="Delta",
            )

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=cast(ReasonAdvancer, RecordingAdvancer()),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()

    assert called
    steps = service.list_steps(thread.id)
    assert len(steps) == 1
    assert steps[0].summary == "Advanced"


def test_run_once_respects_cooldown_after_advance(tmp_path: Path) -> None:
    service = ReasonService(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test cooldown")

    class Advancer:
        def advance(self, t: ReasoningThread) -> ReasoningStep | None:
            return ReasoningStep(
                thread_id=t.id,
                kind="progress",
                summary="s",
                delta="d",
            )

    scheduler = ReasonScheduler(
        project_root=tmp_path,
        advancer=cast(ReasonAdvancer, Advancer()),
        service=service,
        interval_seconds=600,
    )
    scheduler.run_once()

    updated = service.show_thread(thread.id)
    assert updated.skip_next_advance_until is not None
    cooldown = datetime.fromisoformat(updated.skip_next_advance_until)
    assert cooldown > datetime.now(UTC)


def _null_advancer() -> ReasonAdvancer:
    class NullAdvancer:
        def advance(self, t: ReasoningThread) -> ReasoningStep | None:
            return None
    return cast(ReasonAdvancer, NullAdvancer())
