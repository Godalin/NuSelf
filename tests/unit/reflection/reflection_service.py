"""Tests for reflection service operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nuself.trace.composition import compose_trace_services
from nuself.config.settings import runtime_paths
from reason_fixtures import ReasonService
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.service import ReflectionService
from tests.backend import owned_backend


def _reason_service(project_root: Path) -> ReasonService:
    return ReasonService(project_root, prompt_generator=_test_prompt_generator)


def _test_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."


def _service(
    project_root: Path,
    repository: ReflectionRepository,
) -> ReflectionService:
    trace = compose_trace_services(
        runtime_paths(project_root),
        owned_backend(project_root),
    ).recorder
    return ReflectionService(
        repository,
        _reason_service(project_root),
        trace,
        ReflectionOrganizer(project_root, repository=repository),
    )


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
        deep_link="nuself://conversation/reflections",
        created_at=now,
        reviewed_at=None,
    )


@pytest.mark.parametrize(
    ("operation", "status"),
    (("dismiss_entry", "dismissed"), ("archive_entry", "archived")),
)
def test_status_operations_persist_resolved_entry(
    tmp_path: Path,
    operation: str,
    status: str,
) -> None:
    repo = ReflectionRepository(
        runtime_paths(tmp_path),
        backend=owned_backend(tmp_path),
    )
    entry = repo.save(_reflection_entry())

    updated = getattr(_service(tmp_path, repo), operation)(entry.id)

    assert updated.status == status
    assert updated.reviewed_at is not None
    assert repo.get(entry.id) == updated


def test_promote_reflection_to_reason_records_trace(tmp_path: Path) -> None:
    repo = ReflectionRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    entry = repo.save(_reflection_entry())
    service = _service(tmp_path, repo)

    conversation = service.promote_to_reason(entry.id)

    assert conversation.topic == entry.title
    assert conversation.working_summary == entry.body
    assert conversation.evidence_refs == (f"reflection:{entry.id}",)
    assert repo.get(entry.id).status == "pending"

    query = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query
    reason_traces = query.list_traces(kind="reason_thread")
    promotion_traces = query.list_traces(kind="promotion")
    assert len(reason_traces) == 1
    assert len(promotion_traces) == 1
    assert promotion_traces[0].inputs == (f"reflection:{entry.id}",)
    assert promotion_traces[0].outputs == (f"reason:{conversation.id}",)
    links = query.links_for(f"reflection:{entry.id}")
    assert len(links) == 1
    assert links[0].target_id == f"reason:{conversation.id}"


def test_promote_rejects_non_pending_reflection(tmp_path: Path) -> None:
    repo = ReflectionRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    entry = repo.save(_reflection_entry()).with_status("archived")
    repo.save(entry)

    service = _service(tmp_path, repo)

    try:
        service.promote_to_reason(entry.id)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "expected 'pending'" in str(exc)
