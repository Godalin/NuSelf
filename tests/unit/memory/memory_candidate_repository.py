from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from pathlib import Path
from typing import cast

import pytest

from nuself.config import runtime_paths
from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEntry,
    MemoryEntryType,
    MemoryEvidence,
)
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import (
    AtomicDeleteDurabilityError,
    AtomicWriteDurabilityError,
    get_default_backend,
)


def test_memory_candidate_repository_crud_and_accept_with_temporal_fields(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Memory has time",
            body="The user wants memories to carry real-world time information.",
            tags=["memory"],
            source_refs=["thread:default:4-6"],
            evidence=[
                MemoryEvidence(
                    source_type="conversation",
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


def test_accept_can_commit_reviewed_entry_with_candidate(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Reviewed atomically",
            body="Auto-accept must finalize the target before the candidate.",
        )
    )

    entry = repo.accept(candidate.id, target_review_state="reviewed")

    assert isinstance(entry, MemoryEntry)
    assert entry.review_state == "reviewed"
    assert memory_entry_repository(tmp_path).get(entry.id) == entry
    assert repo.get(candidate.id).review_state == "accepted"


def test_accept_keeps_unknown_type_quarantined_when_reviewed_requested(
    tmp_path: Path,
) -> None:
    repo = memory_candidate_repository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type=cast(MemoryEntryType, "future_memory_type"),
            title="Future type",
            body="Unknown types must enter recovery instead of bypassing it.",
        )
    )

    entry = repo.accept(candidate.id, target_review_state="reviewed")

    assert isinstance(entry, MemoryEntry)
    assert entry.review_state == "quarantined"
    assert repo.get(candidate.id).review_state == "accepted"


def test_memory_candidate_repository_rejects_candidate(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
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
    entry_repo = memory_entry_repository(tmp_path)
    existing = entry_repo.save(
        MemoryEntry(
            type="belief",
            title="Memory timing",
            body="Memory should include timestamps.",
            source_refs=["thread:default:0-2"],
        )
    )
    candidate_repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = candidate_repo.save(
        MemoryCandidate(
            type="belief",
            title="Memory timing model",
            body="Memory should preserve real-world timing so changes in thought remain visible.",
            source_refs=["thread:default:4-6"],
            evidence=[MemoryEvidence(source_type="conversation", source_ref="thread:default:4-6", summary="Follow-up")],
            observed_at="2026-05-07",
            relations={"related_to": [existing.id]},
        )
    )

    merged = candidate_repo.merge(candidate.id, existing.id)

    assert merged.id == existing.id
    assert merged.title == "Memory timing model"
    assert merged.source_refs == (
        "thread:default:0-2",
        "thread:default:4-6",
    )
    assert merged.evidence[0].summary == "Follow-up"
    assert merged.observed_at == "2026-05-07"
    assert merged.relations.get("related_to") == (existing.id,)
    assert candidate_repo.get(candidate.id).review_state == "accepted"


def test_memory_candidate_repository_accepts_profile_fact_into_profile_repository(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
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
    profile_repo = ProfileItemRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))
    profile_item = profile_repo.list()[0]

    assert profile_item.title == "Prefers concise output"
    assert accepted.id == profile_item.id
    assert repo.get(candidate.id).review_state == "accepted"
    assert repo.get(candidate.id).target_entry_id == profile_item.id


@pytest.mark.parametrize("target_type", ["memory", "profile"])
def test_accept_create_rolls_back_target_when_candidate_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_type: str,
) -> None:
    repo = memory_candidate_repository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="profile_fact" if target_type == "profile" else "belief",
            title="Atomic candidate",
            body="The target must not outlive a failed candidate commit.",
        )
    )
    operation_error = OSError("candidate commit failed")

    def fail_accepted_save(updated: MemoryCandidate) -> MemoryCandidate:
        if updated.review_state == "accepted":
            raise operation_error
        return updated

    monkeypatch.setattr(repo, "save", fail_accepted_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id)

    assert captured.value is operation_error
    assert repo.get(candidate.id).review_state == "pending"
    assert memory_entry_repository(tmp_path).list() == []
    assert ProfileItemRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path)).list() == []


def test_accept_create_rolls_back_when_review_promotion_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Promotion boundary",
            body="A failed reviewed write must not finalize the candidate.",
        )
    )
    operation_error = OSError("review promotion failed")
    original_save = entry_repo.save

    def fail_reviewed_save(entry: MemoryEntry) -> MemoryEntry:
        if entry.review_state == "reviewed":
            raise operation_error
        return original_save(entry)

    monkeypatch.setattr(entry_repo, "save", fail_reviewed_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id, target_review_state="reviewed")

    assert captured.value is operation_error
    assert entry_repo.list() == []
    assert repo.get(candidate.id).review_state == "pending"


def test_accept_merge_restores_target_when_candidate_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    original = entry_repo.save(
        MemoryEntry(
            type="belief",
            title="Original",
            body="Original body.",
            source_refs=["source:original"],
        )
    )
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            action="update",
            type="belief",
            title="Changed",
            body="Changed body.",
            source_refs=["source:update"],
            target_entry_id=original.id,
        )
    )
    operation_error = OSError("candidate commit failed")

    def fail_accepted_save(updated: MemoryCandidate) -> MemoryCandidate:
        if updated.review_state == "accepted":
            raise operation_error
        return updated

    monkeypatch.setattr(repo, "save", fail_accepted_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id)

    assert captured.value is operation_error
    assert entry_repo.get(original.id) == original
    assert repo.get(candidate.id).review_state == "pending"


def test_accept_merge_restores_target_when_review_promotion_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    original = entry_repo.save(
        MemoryEntry(
            type="belief",
            title="Original",
            body="The exact target must survive a promotion failure.",
        )
    )
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(
            action="update",
            type="belief",
            title="Changed",
            body="This mutation must be compensated.",
            target_entry_id=original.id,
        )
    )
    operation_error = OSError("review promotion failed")
    original_save = entry_repo.save

    def fail_reviewed_save(entry: MemoryEntry) -> MemoryEntry:
        if entry.review_state == "reviewed":
            raise operation_error
        return original_save(entry)

    monkeypatch.setattr(entry_repo, "save", fail_reviewed_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id, target_review_state="reviewed")

    assert captured.value is operation_error
    assert entry_repo.get(original.id) == original
    assert repo.get(candidate.id).review_state == "pending"


def test_accept_delete_restores_target_when_candidate_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    original = entry_repo.save(
        MemoryEntry(
            type="belief",
            title="Retained",
            body="Deletion must roll back.",
        )
    )
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            action="delete",
            type="belief",
            title=original.title,
            body=original.body,
            target_entry_id=original.id,
        )
    )
    operation_error = OSError("candidate commit failed")

    def fail_accepted_save(updated: MemoryCandidate) -> MemoryCandidate:
        if updated.review_state == "accepted":
            raise operation_error
        return updated

    monkeypatch.setattr(repo, "save", fail_accepted_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id)

    assert captured.value is operation_error
    assert entry_repo.get(original.id) == original
    assert repo.get(candidate.id).review_state == "pending"


def test_accept_rolls_back_when_candidate_write_reports_durability_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(type="belief", title="Visible", body="Keep both records.")
    )
    original_save = repo.save
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "candidate.json",
        sync_error=OSError("directory sync failed"),
    )

    def save_then_fail_once(updated: MemoryCandidate) -> MemoryCandidate:
        saved = original_save(updated)
        if updated.review_state == "accepted":
            monkeypatch.setattr(repo, "save", original_save)
            raise durability_error
        return saved

    monkeypatch.setattr(repo, "save", save_then_fail_once)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    accepted = repo.get(candidate.id)
    assert captured.value is durability_error
    assert accepted.review_state == "pending"
    assert accepted.target_entry_id is None
    assert entry_repo.list() == []


def test_accept_rolls_back_without_candidate_readback_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Unknown candidate state",
            body="Do not compensate after observation fails.",
        )
    )
    original_save = repo.save
    original_get = repo.get
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "candidate.json",
        sync_error=OSError("directory sync failed"),
    )
    observation_error = OSError("candidate readback failed")

    def fail_candidate_readback(candidate_id: str) -> MemoryCandidate:
        del candidate_id
        raise observation_error

    def save_then_make_readback_fail(
        updated: MemoryCandidate,
    ) -> MemoryCandidate:
        saved = original_save(updated)
        if updated.review_state == "accepted":
            monkeypatch.setattr(
                repo,
                "get",
                fail_candidate_readback,
            )
            raise durability_error
        return saved

    monkeypatch.setattr(repo, "save", save_then_make_readback_fail)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    monkeypatch.setattr(repo, "get", original_get)
    accepted = repo.get(candidate.id)
    assert captured.value is durability_error
    assert accepted.review_state == "pending"
    assert accepted.target_entry_id is None
    assert entry_repo.list() == []


def test_accept_rolls_back_without_target_readback_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Unknown target state",
            body="Do not delete the visible target.",
        )
    )
    original_save = repo.save
    original_entry_get = entry_repo.get
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "candidate.json",
        sync_error=OSError("directory sync failed"),
    )
    observation_error = OSError("target readback failed")

    def fail_target_readback(entry_id: str) -> MemoryEntry:
        del entry_id
        raise observation_error

    def save_then_make_target_readback_fail(
        updated: MemoryCandidate,
    ) -> MemoryCandidate:
        saved = original_save(updated)
        if updated.review_state == "accepted":
            monkeypatch.setattr(
                entry_repo,
                "get",
                fail_target_readback,
            )
            raise durability_error
        return saved

    monkeypatch.setattr(
        repo,
        "save",
        save_then_make_target_readback_fail,
    )

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    monkeypatch.setattr(entry_repo, "get", original_entry_get)
    accepted = repo.get(candidate.id)
    assert captured.value is durability_error
    assert accepted.target_entry_id is None
    assert entry_repo.list() == []


def test_accept_rolls_back_concurrent_target_change_in_same_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Expected target",
            body="A concurrent visible state must be preserved.",
        )
    )
    original_save = repo.save
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "candidate.json",
        sync_error=OSError("directory sync failed"),
    )

    def save_then_change_target(
        updated: MemoryCandidate,
    ) -> MemoryCandidate:
        saved = original_save(updated)
        if updated.review_state == "accepted":
            target = entry_repo.get(updated.target_entry_id or "")
            entry_repo.save(target.with_updates(title="Unexpected target"))
            raise durability_error
        return saved

    monkeypatch.setattr(repo, "save", save_then_change_target)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    accepted = repo.get(candidate.id)
    assert captured.value is durability_error
    assert accepted.target_entry_id is None
    assert entry_repo.list() == []


def test_accept_rolls_back_new_target_when_target_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(type="belief", title="Rollback", body="Remove target.")
    )
    original_save = entry_repo.save
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "entry.json",
        sync_error=OSError("directory sync failed"),
    )

    def save_then_fail_once(entry: MemoryEntry) -> MemoryEntry:
        original_save(entry)
        monkeypatch.setattr(entry_repo, "save", original_save)
        raise durability_error

    monkeypatch.setattr(entry_repo, "save", save_then_fail_once)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    assert captured.value is durability_error
    assert entry_repo.list() == []
    assert repo.get(candidate.id).review_state == "pending"


def test_merge_rolls_back_previous_target_when_target_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    original = entry_repo.save(
        MemoryEntry(type="belief", title="Before", body="Original body.")
    )
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(
            action="update",
            type="belief",
            title="After",
            body="Updated body.",
            target_entry_id=original.id,
        )
    )
    original_save = entry_repo.save
    durability_error = AtomicWriteDurabilityError(
        tmp_path / "entry.json",
        sync_error=OSError("directory sync failed"),
    )

    def save_then_fail_once(entry: MemoryEntry) -> MemoryEntry:
        original_save(entry)
        monkeypatch.setattr(entry_repo, "save", original_save)
        raise durability_error

    monkeypatch.setattr(entry_repo, "save", save_then_fail_once)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        repo.accept(candidate.id)

    assert captured.value is durability_error
    assert entry_repo.get(original.id) == original
    assert repo.get(candidate.id).review_state == "pending"


def test_delete_rolls_back_target_when_delete_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    original = entry_repo.save(
        MemoryEntry(type="belief", title="Restore", body="Deletion is uncertain.")
    )
    repo = memory_candidate_repository(tmp_path, entry_repository=entry_repo)
    candidate = repo.save(
        MemoryCandidate(
            action="delete",
            type="belief",
            title=original.title,
            body=original.body,
            target_entry_id=original.id,
        )
    )
    original_delete = entry_repo.delete
    durability_error = AtomicDeleteDurabilityError(
        tmp_path / "entry.json",
        sync_error=OSError("directory sync failed"),
    )

    def delete_then_fail_once(entry_id: str) -> None:
        original_delete(entry_id)
        monkeypatch.setattr(entry_repo, "delete", original_delete)
        raise durability_error

    monkeypatch.setattr(entry_repo, "delete", delete_then_fail_once)

    with pytest.raises(AtomicDeleteDurabilityError) as captured:
        repo.accept(candidate.id)

    assert captured.value is durability_error
    assert entry_repo.get(original.id) == original
    assert repo.get(candidate.id).review_state == "pending"


def test_accept_propagates_commit_failure_after_transaction_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    repo = memory_candidate_repository(
        tmp_path,
        entry_repository=entry_repo,
    )
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Double failure",
            body="Both failures must remain inspectable.",
        )
    )
    operation_error = OSError("candidate commit failed")

    def fail_accepted_save(updated: MemoryCandidate) -> MemoryCandidate:
        if updated.review_state == "accepted":
            raise operation_error
        return updated

    monkeypatch.setattr(repo, "save", fail_accepted_save)

    with pytest.raises(OSError) as captured:
        repo.accept(candidate.id)

    assert captured.value is operation_error
    assert entry_repo.list() == []
    assert repo.get(candidate.id).review_state == "pending"


def test_memory_candidate_repository_missing_candidate(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)

    try:
        repo.get("missing")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_edit_updates_fields(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
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
    repo = memory_candidate_repository(tmp_path)
    try:
        repo.reject("missing-id")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_merge_missing_raises(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
    try:
        repo.merge("missing-id", "entry-id")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


def test_memory_candidate_repository_list_excludes_reviewed_by_default(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
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
        evidence=[MemoryEvidence(source_type="conversation", source_ref="t:1", summary="s")],
    )
    obj = candidate.to_memory_object()

    assert obj.type == "belief"
    assert obj.payload["title"] == "Test"
    assert obj.payload["body"] == "Body"
    assert obj.payload["tags"] == ("tag1",)
    assert obj.confidence == 0.8
    assert obj.source_refs == ("ref1",)
    assert obj.metadata["candidate_schema"] == "MemoryCandidate/v1"
    assert len(cast(list[object], obj.payload.get("evidence", []))) == 1


def test_memory_candidate_repository_edit_missing_raises(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
    try:
        repo.edit("missing-id", title="New")
    except MemoryCandidateNotFound:
        return
    raise AssertionError("expected MemoryCandidateNotFound")


@pytest.mark.parametrize("importance", [0.0, 0.85, 1.0])
def test_memory_candidate_importance_roundtrip_and_accept(
    tmp_path: Path,
    importance: float,
) -> None:
    repo = memory_candidate_repository(tmp_path)
    candidate = repo.save(
        MemoryCandidate(
            type="belief",
            title="Importance candidate",
            body="This candidate has custom importance.",
            importance=importance,
        )
    )
    assert repo.get(candidate.id).importance == importance

    wire = candidate.to_wire()
    assert wire["importance"] == importance
    restored = MemoryCandidate.from_wire(wire)
    assert restored.importance == importance

    entry = candidate.to_entry()
    assert entry.importance == importance

    accepted = repo.accept(candidate.id)
    assert isinstance(accepted, MemoryEntry)
    assert accepted.importance == importance


def test_memory_candidate_importance_defaults_only_when_missing() -> None:
    wire = MemoryCandidate(
        type="belief",
        title="Importance default",
        body="Missing importance uses the schema default.",
    ).to_wire()
    del wire["importance"]

    assert MemoryCandidate.from_wire(wire).importance == 0.5

    wire["importance"] = True
    with pytest.raises(ValueError, match="number"):
        MemoryCandidate.from_wire(wire)


@pytest.mark.parametrize("field_name", ["supersedes", "related_memory_ids"])
def test_memory_candidate_rejects_obsolete_relation_fields(
    field_name: str,
) -> None:
    wire = MemoryCandidate(
        type="belief",
        title="Canonical relations",
        body="Candidates use the relations object.",
    ).to_wire()
    wire[field_name] = ["mem_old"]

    with pytest.raises(ValueError, match="obsolete memory relation"):
        MemoryCandidate.from_wire(wire)


def test_memory_candidate_edit_importance(tmp_path: Path) -> None:
    repo = memory_candidate_repository(tmp_path)
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
