from __future__ import annotations

from pathlib import Path

import pytest

from nuself.config import runtime_paths
from nuself.logs import read_log_events
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.storage import get_default_backend


def _entry(entry_id: str, *, title: str, body: str, score: float, created_at: str) -> ReflectionEntry:
    return ReflectionEntry(
        id=entry_id,
        title=title,
        body=body,
        candidate_type="question",
        confidence=score,
        novelty=score,
        urgency=0.3,
        interruption_cost=0.1,
        composite_score=score,
        status="pending",
        discussion_approved=None,
        discussion_trace=(),
        deep_link="nuself://thread/reflections",
        created_at=created_at,
        reviewed_at=None,
    )


def test_reflection_organizer_merges_similar_pending_entries(tmp_path: Path) -> None:
    repo = ReflectionRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))
    weaker = repo.add(
        _entry(
            "reflection-a",
            title="Memory trace design",
            body="Think about memory trace design and provenance links.",
            score=0.5,
            created_at="2026-05-18T10:00:00+00:00",
        )
    )
    stronger = repo.add(
        _entry(
            "reflection-b",
            title="Memory trace provenance design",
            body="Explore memory trace design and provenance links in NuSelf.",
            score=0.9,
            created_at="2026-05-18T10:01:00+00:00",
        )
    )

    result = ReflectionOrganizer(tmp_path).organize_pending()

    assert result.merged_groups == 1
    assert result.archived_entries == 1
    kept = repo.get(stronger.id)
    archived = repo.get(weaker.id)
    assert kept.status == "pending"
    assert "Merged similar reflection notes:" in kept.body
    assert archived.status == "archived"
    events = read_log_events(project_root=tmp_path, component="reflection")
    assert events[-1].event == "organizer_completed"
    assert events[-1].metadata == {"merged_groups": 1, "archived_entries": 1}


def test_reflection_organizer_leaves_distinct_entries_pending(tmp_path: Path) -> None:
    repo = ReflectionRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))
    repo.add(
        _entry(
            "reflection-a",
            title="Memory trace design",
            body="Think about memory trace design and provenance links.",
            score=0.5,
            created_at="2026-05-18T10:00:00+00:00",
        )
    )
    repo.add(
        _entry(
            "reflection-b",
            title="Exercise routine",
            body="Consider how morning exercise changes energy.",
            score=0.9,
            created_at="2026-05-18T10:01:00+00:00",
        )
    )

    result = ReflectionOrganizer(tmp_path).organize_pending()

    assert result.merged_groups == 0
    assert result.archived_entries == 0
    assert len(repo.list(status="pending")) == 2


def test_organizer_audit_failure_cannot_replace_merged_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = ReflectionRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))
    weaker = repo.add(
        _entry(
            "reflection-a",
            title="Memory trace design",
            body="Think about memory trace design and provenance links.",
            score=0.5,
            created_at="2026-05-18T10:00:00+00:00",
        )
    )
    stronger = repo.add(
        _entry(
            "reflection-b",
            title="Memory trace provenance design",
            body="Explore memory trace design and provenance links in NuSelf.",
            score=0.9,
            created_at="2026-05-18T10:01:00+00:00",
        )
    )

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

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = ReflectionOrganizer(
            tmp_path,
            repository=repo,
        ).organize_pending()

    assert result.merged_groups == 1
    assert result.archived_entries == 1
    assert repo.get(stronger.id).status == "pending"
    assert repo.get(weaker.id).status == "archived"
