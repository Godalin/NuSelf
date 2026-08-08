from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from pathlib import Path

from nuself.source.record import SourceChunk, SourceDocument
from nuself.source.local import load


def test_source_document_and_chunk_round_trip() -> None:
    document = SourceDocument(
        id="src_test",
        title="Test Source",
        path="/tmp/test.md",
        kind="markdown",
        origin="local",
        privacy="shareable",
        tags=["memory"],
        source_date="2026-05-07",
    )
    chunk = SourceChunk(
        id="src_test_chunk_0000",
        source_id=document.id,
        source_ref="source:src_test:0",
        index=0,
        text="A source chunk.",
        title=document.title,
        path=document.path,
    )

    assert SourceDocument.from_wire(document.to_wire()) == document
    assert SourceChunk.from_wire(chunk.to_wire()) == chunk


def test_load_markdown_source_extracts_metadata_and_chunks(tmp_path: Path) -> None:
    source_path = tmp_path / "note.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Mirror Notes",
                "date: 2026-05-07",
                "tags: [memory, mirror]",
                "origin: journal",
                "privacy: shareable",
                "---",
                "# Ignored Heading",
                "",
                "First paragraph.",
                "",
                "Second paragraph.",
            ]
        ),
        encoding="utf-8",
    )

    document, chunks = load(source_path, tags=["imported"])

    assert document.title == "Mirror Notes"
    assert document.kind == "markdown"
    assert document.origin == "journal"
    assert document.privacy == "shareable"
    assert document.source_date == "2026-05-07"
    assert document.tags == ("memory", "mirror", "imported")
    assert chunks[0].source_id == document.id
    assert chunks[0].source_ref == f"source:{document.id}:0"
    assert "First paragraph." in chunks[0].text


def test_source_repository_appends_changed_content_as_new_revision(tmp_path: Path) -> None:
    source_path = tmp_path / "note.txt"
    source_path.write_text("Local note title\n\nBody text for ingestion.", encoding="utf-8")
    repo = source_repository(tmp_path)

    result = repo.importer.ingest(source_path, tags=["notes"])
    document = repo.query.list()[0]
    chunks = repo.query.chunks(document.id)

    assert result.documents == 1
    assert result.chunks == 1
    assert repo.query.get(document.id) == document
    assert document.title == "Local note title"
    assert document.tags == ("notes",)
    assert chunks[0].source_ref == f"source:{document.id}:0"

    source_path.write_text("Local note title\n\nUpdated body.", encoding="utf-8")
    second_result = repo.importer.ingest(source_path)

    assert second_result.documents == 1
    assert second_result.chunks == 1
    assert second_result.documents == 1
    assert len(repo.query.list()) == 2
    assert repo.query.chunks(document.id)[0].text == (
        "Local note title\n\nBody text for ingestion."
    )
    assert any(
        chunk.text == "Local note title\n\nUpdated body."
        for chunk in repo.query.chunks()
    )


def test_source_repository_search_returns_ranked_chunks_with_metadata(tmp_path: Path) -> None:
    first_path = tmp_path / "memory.md"
    first_path.write_text(
        "\n".join(
            [
                "---",
                "title: Memory Architecture",
                "tags: [memory]",
                "origin: notes",
                "---",
                "Source chunks should keep stable references.",
            ]
        ),
        encoding="utf-8",
    )
    second_path = tmp_path / "other.txt"
    second_path.write_text("Cooking note\n\nUnrelated text.", encoding="utf-8")
    repo = source_repository(tmp_path)
    repo.importer.ingest(tmp_path)

    matches = repo.query.search("stable memory references")

    assert len(matches) == 1
    assert matches[0].document.title == "Memory Architecture"
    assert matches[0].chunk.source_ref == f"source:{matches[0].document.id}:0"
    assert "text" in matches[0].reasons
    assert "tag" in matches[0].reasons


def test_source_reimport_is_idempotent_and_has_no_memory_side_effects(tmp_path: Path) -> None:
    source_path = tmp_path / "profile.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Profile Source",
                "tags: [mirror]",
                "date: 2026-05-07",
                "---",
                "A source paragraph about durable preferences.",
            ]
        ),
        encoding="utf-8",
    )
    repo = source_repository(tmp_path)
    first = repo.importer.ingest(source_path)
    second = repo.importer.ingest(source_path)
    assert first.documents == 1
    assert second.documents == 0
    assert second.unchanged == 1
    assert len(repo.query.list()) == 1
    assert len(repo.query.chunks()) == 1
