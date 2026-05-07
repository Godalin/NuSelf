from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import (
    MemoryEntry,
    MemoryObject,
    MemoryValidationError,
    default_memory_type_registry,
)
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository
from nuself.memory.repository import MemorySearchFilters, memory_stats


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


def test_memory_entry_has_memory_object_migration_shape() -> None:
    entry = MemoryEntry(
        type="preference",
        title="CLI output style",
        body="The user prefers concise command output.",
        tags=["cli"],
        source_refs=["thread:default:0-2"],
        confidence=0.8,
        review_state="reviewed",
    )

    memory = entry.to_memory_object()
    restored = MemoryEntry.from_memory_object(memory)

    assert memory.type == "preference"
    assert memory.payload["title"] == "CLI output style"
    assert memory.payload["body"] == "The user prefers concise command output."
    assert memory.metadata["entry_schema"] == "MemoryEntry/v1"
    assert restored == entry


def test_default_registry_validates_and_summarizes_built_in_memory_object() -> None:
    registry = default_memory_type_registry()
    memory = MemoryObject(
        type="instruction",
        payload={
            "title": "Validation first",
            "body": "Run focused tests before widening validation.",
            "tags": ["testing"],
            "revisit_at": None,
        },
        confidence=0.9,
        review_state="reviewed",
    )

    registry.validate(memory)

    assert registry.summarize(memory) == "Validation first: Run focused tests before widening validation."


def test_repository_rejects_invalid_descriptor_payload(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    invalid = MemoryEntry(type="belief", title="", body="Missing title.")

    try:
        repo.save(invalid)
    except MemoryValidationError as exc:
        assert exc.memory_type == "belief"
        assert exc.issues[0].field == "payload.title"
        return
    raise AssertionError("expected MemoryValidationError")


def test_repository_accepts_unknown_draft_entry_type_as_migration_escape_hatch(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(MemoryEntry(type="style_trait", title="Concise style", body="Keep summaries compact."))

    assert repo.get(entry.id).title == "Concise style"


def test_memory_repository_search_filters_and_stats(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Temporal memory",
            body="Memory should preserve time.",
            tags=["memory"],
            review_state="reviewed",
            observed_at="2026-05-07",
        )
    )
    repo.save(
        MemoryEntry(
            type="episode",
            title="Other event",
            body="A different event.",
            tags=["event"],
        )
    )

    filtered = repo.search(
        "memory",
        MemorySearchFilters(type="belief", tag="memory", review_state="reviewed", observed_from="2026-05-01"),
    )
    stats = memory_stats(tmp_path)

    assert [entry.title for entry in filtered] == ["Temporal memory"]
    assert stats.entries_total == 2
    assert stats.entries_by_type == {"belief": 1, "episode": 1}
    assert stats.entries_by_review_state["reviewed"] == 1
    assert stats.entries_with_observed_at == 1
