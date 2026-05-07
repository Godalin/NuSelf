from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from nuself.domain.source import SourceChunk, SourceDocument
from nuself.memory.source_repository import SourceRepository, load_source_file


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

    document, chunks = load_source_file(source_path, tags=["imported"])

    assert document.title == "Mirror Notes"
    assert document.kind == "markdown"
    assert document.origin == "journal"
    assert document.privacy == "shareable"
    assert document.source_date == "2026-05-07"
    assert document.tags == ["memory", "mirror", "imported"]
    assert chunks[0].source_id == document.id
    assert chunks[0].source_ref == f"source:{document.id}:0"
    assert "First paragraph." in chunks[0].text


def test_source_repository_ingests_file_and_replaces_chunks(tmp_path: Path) -> None:
    source_path = tmp_path / "note.txt"
    source_path.write_text("Local note title\n\nBody text for ingestion.", encoding="utf-8")
    repo = SourceRepository(tmp_path)

    result = repo.ingest_path(source_path, tags=["notes"])
    document = repo.list_documents()[0]
    chunks = repo.list_chunks(document.id)

    assert result.documents == 1
    assert result.chunks == 1
    assert repo.get_document(document.id) == document
    assert document.title == "Local note title"
    assert document.tags == ["notes"]
    assert chunks[0].source_ref == f"source:{document.id}:0"

    source_path.write_text("Local note title\n\nUpdated body.", encoding="utf-8")
    second_result = repo.ingest_path(source_path)

    assert second_result.documents == 1
    assert second_result.chunks == 1
    assert len(repo.list_chunks(document.id)) == 1
    assert repo.list_chunks(document.id)[0].text == "Local note title\n\nUpdated body."


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
    repo = SourceRepository(tmp_path)
    repo.ingest_path(tmp_path)

    matches = repo.search("stable memory references")

    assert len(matches) == 1
    assert matches[0].document.title == "Memory Architecture"
    assert matches[0].chunk.source_ref == f"source:{matches[0].document.id}:0"
    assert "text" in matches[0].reasons
    assert "tag" in matches[0].reasons


def test_source_repository_reindex_writes_source_index(tmp_path: Path) -> None:
    source_path = tmp_path / "note.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Indexed Source",
                "tags: [index]",
                "privacy: shareable",
                "---",
                "Indexed source body.",
            ]
        ),
        encoding="utf-8",
    )
    repo = SourceRepository(tmp_path)
    repo.ingest_path(source_path)

    index_path = repo.reindex()
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    index = cast(list[dict[str, object]], raw)

    assert index_path == tmp_path / "private" / "derived" / "source_index.json"
    assert len(index) == 1
    assert index[0]["title"] == "Indexed Source"
    assert index[0]["document_privacy"] == "shareable"
    assert index[0]["source_ref"] == f"source:{index[0]['source_id']}:0"


def test_source_repository_extracts_profile_candidates(tmp_path: Path) -> None:
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
    repo = SourceRepository(tmp_path)
    repo.ingest_path(source_path)
    document = repo.list_documents()[0]

    candidates = repo.extract_candidates(document.id)

    assert len(candidates) == 1
    assert candidates[0].type == "profile_fact"
    assert candidates[0].source_refs == [f"source:{document.id}:0"]
    assert candidates[0].evidence[0].source_type == "source"
    assert candidates[0].evidence[0].source_ref == candidates[0].source_refs[0]
