"""Tests for reflection service operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.reflection.service import ReflectionService
from nuself.trace.service import TraceQueryService


def _reflection_entry(entry_id: str = "reflection-test") -> ReflectionEntry:
    now = datetime.now(UTC).isoformat()
    return ReflectionEntry(
        id=entry_id,
        title="Investigate a recurring idea",
        body="The body should become the initial reason working summary.",
        candidate_type="question",
        confidence=0.8,
        novelty=0.7,
        urgency=0.4,
        interruption_cost=0.2,
        composite_score=0.6,
        status="pending",
        discussion_approved=True,
        discussion_trace=(),
        deep_link="nuself://thread/reflections",
        created_at=now,
        reviewed_at=None,
    )


def test_promote_reflection_to_reason_records_trace(tmp_path: Path) -> None:
    repo = ReflectionRepository(tmp_path)
    entry = repo.add(_reflection_entry())
    service = ReflectionService(tmp_path, repository=repo, reason_service=ReasonService(tmp_path))

    thread = service.promote_to_reason(entry.id)

    assert thread.question == entry.title
    assert thread.working_summary == entry.body
    assert thread.evidence_refs == [f"reflection:{entry.id}"]
    assert repo.get(entry.id).status == "pending"

    query = TraceQueryService(tmp_path)
    reason_traces = query.list_traces(kind="reason_thread")
    promotion_traces = query.list_traces(kind="promotion")
    assert len(reason_traces) == 1
    assert len(promotion_traces) == 1
    assert promotion_traces[0].inputs == [f"reflection:{entry.id}"]
    assert promotion_traces[0].outputs == [f"reason:{thread.id}"]
    links = query.links_for(f"reflection:{entry.id}")
    assert len(links) == 1
    assert links[0].target_id == f"reason:{thread.id}"


def test_promote_rejects_non_pending_reflection(tmp_path: Path) -> None:
    repo = ReflectionRepository(tmp_path)
    entry = repo.add(_reflection_entry()).with_status("archived")
    repo.update(entry)

    service = ReflectionService(tmp_path, repository=repo, reason_service=ReasonService(tmp_path))

    try:
        service.promote_to_reason(entry.id)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "expected 'pending'" in str(exc)
