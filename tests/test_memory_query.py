from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository


def test_memory_query_ranks_relevant_entries_with_reasons(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    relevant = repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
            review_state="reviewed",
        )
    )
    repo.save(
        MemoryEntry(
            type="episode",
            title="Unrelated dinner note",
            body="We talked about food.",
            tags=["daily"],
        )
    )
    service = MemoryQueryService(repo)

    matches = service.search(MemoryQuery(text="clarity and assumptions"))

    assert [match.entry.id for match in matches] == [relevant.id]
    assert "title" in matches[0].reasons
    assert "body" in matches[0].reasons
    assert "reviewed" in matches[0].reasons


def test_memory_query_packs_context_with_metadata(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
        )
    )
    service = MemoryQueryService(repo)

    packed = service.pack(MemoryQuery(text="direct style"))

    assert len(packed.matches) == 1
    assert entry.id in packed.text
    assert "type=style_trait" in packed.text
    assert "match=" in packed.text


def test_memory_query_returns_empty_context_for_irrelevant_query(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    service = MemoryQueryService(repo)

    packed = service.pack(MemoryQuery(text="weather forecast"))

    assert packed.text == ""
    assert packed.matches == ()
