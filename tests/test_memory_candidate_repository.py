from __future__ import annotations

from pathlib import Path
from typing import cast

from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.profile.repository import ProfileItemRepository


def test_memory_candidate_repository_crud_and_accept_with_temporal_fields(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Memory has time",
            body="The user wants memories to carry real-world time information.",
            tags=["memory"],
            source_refs=["thread:default:4-6"],
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref="thread:default:4-6",
                    summary="User asked for realistic temporal memory.",
                    observed_at="2026-05-07",
                )
            ],
            observed_at="2026-05-07",
            valid_from="2026-05-07",
            temporal_note="Raised while discussing realistic memory evolution.",
        )
    )

    listed = repo.list()
    entry = repo.accept(candidate.id)
    accepted = repo.get(candidate.id)

    assert listed == [candidate]
    assert entry.title == "Memory has time"
    assert entry.observed_at == "2026-05-07"
    assert entry.valid_from == "2026-05-07"
    assert entry.temporal_note == "Raised while discussing realistic memory evolution."
    assert entry.evidence[0].source_ref == "thread:default:4-6"
    assert entry.evidence[0].summary == "User asked for realistic temporal memory."
    assert accepted.review_state == "accepted"
    assert accepted.target_entry_id == entry.id
    assert repo.list() == []
    assert repo.list(include_reviewed=True)[0].id == candidate.id


def test_memory_candidate_repository_rejects_candidate(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="episode",
            title="Low value note",
            body="A proposed memory that should not be accepted.",
        )
    )

    rejected = repo.reject(candidate.id)

    assert rejected.review_state == "rejected"
    assert repo.list() == []


def test_memory_candidate_repository_merges_into_existing_entry(tmp_path: Path) -> None:
    entry_repo = MemoryEntryRepository(tmp_path)
    existing = entry_repo.save(
        MemoryEntry(
            type="belief",
            title="Memory timing",
            body="Memory should include timestamps.",
            source_refs=["thread:default:0-2"],
        )
    )
    candidate_repo = MemoryCandidateRepository(tmp_path, entry_repository=entry_repo)
    candidate = candidate_repo.save(
        MemoryCandidate(
            type="belief",
            title="Memory timing model",
            body="Memory should preserve real-world timing so changes in thought remain visible.",
            source_refs=["thread:default:4-6"],
            evidence=[MemoryEvidence(source_type="thread", source_ref="thread:default:4-6", summary="Follow-up")],
            observed_at="2026-05-07",
            relations={"related_to": [existing.id]},
        )
    )

    merged = candidate_repo.merge(candidate.id, existing.id)

    assert merged.id == existing.id
    assert merged.title == "Memory timing model"
    assert merged.source_refs == ["thread:default:0-2", "thread:default:4-6"]
    assert merged.evidence[0].summary == "Follow-up"
    assert merged.observed_at == "2026-05-07"
    assert merged.relations.get("related_to") == [existing.id]
    assert candidate_repo.get(candidate.id).review_state == "accepted"


def test_memory_candidate_repository_accepts_profile_fact_into_profile_repository(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="profile_fact",
            title="Prefers concise output",
            body="The user wants crisp, doc-aligned answers.",
            source_refs=["source:profile:0"],
            evidence=[MemoryEvidence(source_type="source", source_ref="source:profile:0", summary="Imported")],
        )
    )

    accepted = repo.accept(candidate.id)
    profile_repo = ProfileItemRepository(tmp_path)
    profile_item = profile_repo.list()[0]

    assert profile_item.title == "Prefers concise output"
    assert accepted.id == profile_item.id
    assert repo.get(candidate.id).review_state == "accepted"
    assert repo.get(candidate.id).target_entry_id == profile_item.id


def test_memory_candidate_repository_missing_candidate(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)

    try:
        repo.get("missing")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_edit_updates_fields(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(type="belief", title="Old", body="Old body.")
    )

    updated = repo.edit(candidate.id, title="New", body="New body.")

    got = repo.get(candidate.id)
    assert got.title == "New"
    assert got.body == "New body."
    assert updated.title == "New"
    assert updated.body == "New body."


def test_memory_candidate_repository_reject_missing_raises(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    try:
        repo.reject("missing-id")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_merge_missing_raises(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    try:
        repo.merge("missing-id", "entry-id")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_list_excludes_reviewed_by_default(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(MemoryCandidate(type="belief", title="Test", body="Body."))
    repo.accept(candidate.id)

    assert repo.list() == []
    assert len(repo.list(include_reviewed=True)) == 1


def test_memory_candidate_to_memory_object_round_trip() -> None:
    candidate = MemoryCandidate(
        type="belief",
        title="Test",
        body="Body",
        tags=["tag1"],
        source_refs=["ref1"],
        confidence=0.8,
        evidence=[MemoryEvidence(source_type="thread", source_ref="t:1", summary="s")],
    )
    obj = candidate.to_memory_object()

    assert obj.type == "belief"
    assert obj.payload["title"] == "Test"
    assert obj.payload["body"] == "Body"
    assert obj.payload["tags"] == ["tag1"]
    assert obj.confidence == 0.8
    assert obj.source_refs == ["ref1"]
    assert obj.metadata["candidate_schema"] == "MemoryCandidate/v1"
    assert len(cast(list[object], obj.payload.get("evidence", []))) == 1


def test_memory_candidate_repository_edit_missing_raises(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    try:
        repo.edit("missing-id", title="New")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_importance_roundtrip_and_accept(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Importance candidate",
            body="This candidate has custom importance.",
            importance=0.85,
        )
    )
    assert repo.get(candidate.id).importance == 0.85

    wire = candidate.to_wire()
    assert wire["importance"] == 0.85
    restored = MemoryCandidate.from_wire(wire)
    assert restored.importance == 0.85

    entry = candidate.to_entry()
    assert entry.importance == 0.85

    accepted = repo.accept(candidate.id)
    assert isinstance(accepted, MemoryEntry)
    assert accepted.importance == 0.85


def test_memory_candidate_edit_importance(tmp_path: Path) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Edit importance",
            body="Body",
        )
    )
    updated = repo.edit(candidate.id, importance=0.95)
    assert updated.importance == 0.95
    loaded = repo.get(candidate.id)
    assert loaded.importance == 0.95
