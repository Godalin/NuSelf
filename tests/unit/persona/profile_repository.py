from __future__ import annotations

from pathlib import Path
import pytest

from nuself.config.settings import runtime_paths
from nuself.memory.model import MemoryEvidence
from nuself.profile.model import ProfileItem
from nuself.profile.repository import (
    ProfileItemNotFound,
    ProfileItemRepository,
    ProfileSearchFilters,
)
from tests.backend import owned_backend


def _repository(root: Path) -> ProfileItemRepository:
    return ProfileItemRepository(
        runtime_paths(root),
        backend=owned_backend(root),
    )


def test_profile_repository_crud(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    item = repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli"],
            source_refs=["source:abc:0"],
            evidence=[
                MemoryEvidence(
                    source_type="source",
                    source_ref="source:abc:0",
                    summary="Imported from sample source",
                    quote="Prefers concise command output.",
                )
            ],
            observed_at="2026-05-07",
        )
    )

    assert repo.get(item.id).title == "Concise output"
    assert repo.list()[0].id == item.id

    updated = item.with_updates(title="Concise CLI output")
    repo.save(updated)

    assert repo.get(item.id).title == "Concise CLI output"

    repo.delete(item.id)
    assert repo.list() == []


def test_profile_repository_missing_item(tmp_path: Path) -> None:
    repo = _repository(tmp_path)

    try:
        repo.get("missing")
    except ProfileItemNotFound:
        return
    raise AssertionError("expected ProfileItemNotFound")


def test_profile_repository_search_filters_and_text_match(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli", "style"],
            source_refs=["source:abc:0"],
            observed_at="2026-05-07",
            valid_from="2026-05-07",
        )
    )
    repo.save(
        ProfileItem(
            type="profile_fact",
            title="Long-form output",
            body="Likes detailed summaries.",
            tags=["docs"],
            source_refs=["source:def:0"],
            observed_at="2026-05-08",
        )
    )

    filtered = repo.search(
        "concise",
        ProfileSearchFilters(type="profile_fact", tag="style", observed_from="2026-05-01", valid_on="2026-05-07"),
    )

    assert [item.title for item in filtered] == ["Concise output"]


def test_profile_repository_delete_missing_raises(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    try:
        repo.delete("missing-id")
    except ProfileItemNotFound:
        return
    raise AssertionError("expected ProfileItemNotFound")


def test_profile_repository_search_no_matches_returns_empty(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    repo.save(ProfileItem(type="profile_fact", title="Style", body="Concise."))

    results = repo.search("xyz")
    assert results == []


def test_profile_item_with_updates_preserves_unmodified_fields(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    original = ProfileItem(
        type="profile_fact",
        title="Original",
        body="Original body.",
        tags=["a", "b"],
        confidence=0.9,
    )
    repo.save(original)

    updated = original.with_updates(title="Updated")
    repo.save(updated)

    loaded = repo.get(original.id)
    assert loaded.title == "Updated"
    assert loaded.body == "Original body."
    assert loaded.tags == ("a", "b")
    assert loaded.confidence == 0.9


@pytest.mark.parametrize("importance", [0.0, 0.85, 1.0])
def test_profile_item_importance_roundtrip(
    tmp_path: Path,
    importance: float,
) -> None:
    repo = _repository(tmp_path)
    item = repo.save(
        ProfileItem(
            type="profile_fact",
            title="Importance test",
            body="This item has custom importance.",
            importance=importance,
        )
    )
    loaded = repo.get(item.id)
    assert loaded.importance == importance

    wire = item.to_wire()
    assert wire["importance"] == importance
    restored = ProfileItem.from_wire(wire)
    assert restored.importance == importance


def test_profile_item_importance_defaults_only_when_missing() -> None:
    wire = ProfileItem(
        type="profile_fact",
        title="Importance default",
        body="Missing importance uses the schema default.",
    ).to_wire()
    del wire["importance"]

    assert ProfileItem.from_wire(wire).importance == 0.5

    wire["importance"] = True
    with pytest.raises(ValueError, match="number"):
        ProfileItem.from_wire(wire)


@pytest.mark.parametrize("field_name", ["supersedes", "related_memory_ids"])
def test_profile_item_rejects_obsolete_relation_fields(
    field_name: str,
) -> None:
    wire = ProfileItem(
        type="profile_fact",
        title="Canonical relations",
        body="Profile relations use one field.",
    ).to_wire()
    wire[field_name] = ["mem_old"]

    with pytest.raises(ValueError, match="obsolete profile relation"):
        ProfileItem.from_wire(wire)


def test_profile_item_with_updates_importance(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    original = ProfileItem(
        type="profile_fact",
        title="Original",
        body="Body",
        importance=0.6,
    )
    repo.save(original)

    updated = original.with_updates(importance=0.95)
    repo.save(updated)

    loaded = repo.get(original.id)
    assert loaded.importance == 0.95
