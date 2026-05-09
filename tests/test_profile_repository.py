from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEvidence
from nuself.domain.profile import ProfileItem
from nuself.profile.repository import ProfileItemNotFound, ProfileItemRepository, ProfileSearchFilters


def test_profile_repository_crud_and_reindex(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
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
    index_path = repo.reindex()

    assert repo.get(item.id).title == "Concise CLI output"
    assert index_path.is_file()

    repo.delete(item.id)
    assert repo.list() == []


def test_profile_repository_missing_item(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)

    try:
        repo.get("missing")
    except ProfileItemNotFound:
        return
    raise AssertionError("expected ProfileItemNotFound")


def test_profile_repository_search_filters_and_text_match(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
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
    repo = ProfileItemRepository(tmp_path)
    try:
        repo.delete("missing-id")
    except ProfileItemNotFound:
        return
    raise AssertionError("expected ProfileItemNotFound")


def test_profile_repository_reindex_on_empty_repo(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
    index_path = repo.reindex()
    assert index_path.is_file()


def test_profile_repository_search_no_matches_returns_empty(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
    repo.save(ProfileItem(type="profile_fact", title="Style", body="Concise."))

    results = repo.search("xyz")
    assert results == []


def test_profile_item_with_updates_preserves_unmodified_fields(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
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
    assert loaded.tags == ["a", "b"]
    assert loaded.confidence == 0.9


def test_profile_item_importance_roundtrip(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
    item = repo.save(
        ProfileItem(
            type="profile_fact",
            title="Importance test",
            body="This item has custom importance.",
            importance=0.85,
        )
    )
    loaded = repo.get(item.id)
    assert loaded.importance == 0.85

    wire = item.to_wire()
    assert wire["importance"] == 0.85
    restored = ProfileItem.from_wire(wire)
    assert restored.importance == 0.85


def test_profile_item_with_updates_importance(tmp_path: Path) -> None:
    repo = ProfileItemRepository(tmp_path)
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
