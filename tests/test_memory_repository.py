from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository


def test_memory_repository_crud_and_reindex(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )

    assert repo.get(entry.id).title == "Clarity matters"
    assert repo.search("assumptions")[0].id == entry.id

    updated = entry.with_updates(title="Clarity matters most")
    repo.save(updated)
    index_path = repo.reindex()

    assert repo.get(entry.id).title == "Clarity matters most"
    assert index_path.is_file()

    repo.delete(entry.id)
    assert repo.list() == []


def test_memory_repository_missing_entry(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)

    try:
        repo.get("missing")
    except MemoryEntryNotFound:
        return
    raise AssertionError("expected MemoryEntryNotFound")

