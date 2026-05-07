from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.domain.profile import ProfileItem
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository


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
    assert "Memory entries:" in packed.text
    assert "type=style_trait" in packed.text
    assert "match=" in packed.text


def test_memory_query_packs_source_chunks_with_references(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Source Context",
                "tags: [retrieval]",
                "---",
                "Source chunks provide durable evidence.",
            ]
        ),
        encoding="utf-8",
    )
    entry_repo = MemoryEntryRepository(tmp_path)
    source_repo = SourceRepository(tmp_path)
    source_repo.ingest_path(source_path)
    service = MemoryQueryService(entry_repo, source_repo)

    packed = service.pack(MemoryQuery(text="durable evidence"))

    assert packed.matches == ()
    assert len(packed.source_matches) == 1
    assert "Source chunks:" in packed.text
    assert "Source Context" in packed.text
    assert "ref=source:" in packed.text
    assert "Source chunks provide durable evidence." in packed.text


def test_memory_query_packs_profile_items_with_references(tmp_path: Path) -> None:
    entry_repo = MemoryEntryRepository(tmp_path)
    profile_repo = ProfileItemRepository(tmp_path)
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli", "style"],
            source_refs=["source:profile:0"],
            observed_at="2026-05-07",
        )
    )
    service = MemoryQueryService(entry_repo, profile_repository=profile_repo)

    packed = service.pack(MemoryQuery(text="concise command"))

    assert len(packed.profile_matches) == 1
    assert packed.matches == ()
    assert "Profile items:" in packed.text
    assert "Concise output" in packed.text
    assert "source:profile:0" in packed.text


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


def test_memory_query_includes_profile_items_in_default_chat_context(tmp_path: Path) -> None:
    profile_repo = ProfileItemRepository(tmp_path)
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
            source_refs=["source:profile:0"],
        )
    )
    service = MemoryQueryService(MemoryEntryRepository(tmp_path), profile_repository=profile_repo)

    packed = service.pack(MemoryQuery(text="direct answers"))

    assert len(packed.profile_matches) == 1
    assert "Profile items:" in packed.text
    assert "Direct style" in packed.text


def test_memory_query_uses_type_descriptor_affinity(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    style = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Concise output",
            body="Keep answers compact and direct.",
            tags=["communication"],
            review_state="reviewed",
        )
    )
    repo.save(
        MemoryEntry(
            type="belief",
            title="Architecture boundary",
            body="File-backed memory is authoritative.",
            tags=["architecture"],
            review_state="reviewed",
        )
    )
    service = MemoryQueryService(repo)

    matches = service.search(MemoryQuery(text="how should you respond"))

    assert [match.entry.id for match in matches] == [style.id]
    assert "type_descriptor" in matches[0].reasons


def test_memory_query_filters_by_type_and_tag(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
            review_state="reviewed",
        )
    )
    goal = repo.save(
        MemoryEntry(
            type="goal",
            title="LangGraph preparation",
            body="Prepare memory tools before graph migration.",
            tags=["runtime"],
            review_state="reviewed",
        )
    )
    service = MemoryQueryService(repo)

    matches = service.search(MemoryQuery(text="current goal", memory_types=("goal",), tags=("runtime",)))

    assert [match.entry.id for match in matches] == [goal.id]
    assert "type_descriptor" in matches[0].reasons
