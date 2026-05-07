from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEvidence
from nuself.domain.profile import ProfileItem
from nuself.profile.repository import ProfileItemNotFound, ProfileItemRepository


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