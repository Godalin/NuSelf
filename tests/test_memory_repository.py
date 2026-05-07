from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from nuself.domain.memory import (
    MemoryEntry,
    MemoryObject,
    MemoryValidationError,
    default_memory_type_registry,
    default_relation_descriptor_registry,
)
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository, MemoryRelationFilters
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


def test_memory_repository_reindex_writes_relation_index(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    old = repo.save(
        MemoryEntry(
            type="belief",
            title="Closed categories",
            body="Memory types are fixed.",
            review_state="reviewed",
        )
    )
    related = repo.save(
        MemoryEntry(
            type="concept",
            title="Relation expansion",
            body="Related memories can travel together during retrieval.",
            review_state="reviewed",
        )
    )
    current = repo.save(
        MemoryEntry(
            type="belief",
            title="Open descriptors",
            body="Memory types are descriptor-backed.",
            review_state="reviewed",
            supersedes=[old.id],
            related_memory_ids=[related.id],
        )
    )

    repo.reindex()
    relation_path = tmp_path / "private" / "derived" / "relation_index.json"
    raw: object = json.loads(relation_path.read_text(encoding="utf-8"))

    assert isinstance(raw, list)
    assert raw == [
        {
            "confidence_policy": "inherits_source",
            "confidence": current.confidence,
            "inverse_relation": "superseded_by",
            "relation": "supersedes",
            "retrieval_rule": "include_both_current_and_superseded",
            "source_id": current.id,
            "source_title": "Open descriptors",
            "source_type": "belief",
            "source_updated_at": current.updated_at,
            "symmetric": False,
            "target_exists": True,
            "target_id": old.id,
            "target_title": "Closed categories",
            "target_type": "belief",
            "temporal_policy": "source_validity_refines_target",
            "transitive": False,
        },
        {
            "confidence_policy": "inherits_source",
            "confidence": current.confidence,
            "inverse_relation": "related_to",
            "relation": "related_to",
            "retrieval_rule": "include_direct_neighbors",
            "source_id": current.id,
            "source_title": "Open descriptors",
            "source_type": "belief",
            "source_updated_at": current.updated_at,
            "symmetric": True,
            "target_exists": True,
            "target_id": related.id,
            "target_title": "Relation expansion",
            "target_type": "concept",
            "temporal_policy": "independent",
            "transitive": False,
        },
    ]

    related_records = repo.list_relations(MemoryRelationFilters(relation="related_to"))

    assert len(related_records) == 1
    assert related_records[0].source_id == current.id
    assert related_records[0].target_id == related.id
    assert related_records[0].relation == "related_to"
    assert related_records[0].symmetric is True
    assert related_records[0].inverse_relation == "related_to"


def test_memory_repository_reindex_writes_symbolic_graph(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    target = repo.save(
        MemoryEntry(
            type="concept",
            title="Graph projection",
            body="A derived graph should remain rebuildable.",
            tags=["graph"],
            review_state="reviewed",
        )
    )
    source = repo.save(
        MemoryEntry(
            type="belief",
            title="Graph source",
            body="Memory entries can become graph nodes.",
            tags=["graph"],
            review_state="reviewed",
            related_memory_ids=[target.id],
        )
    )

    repo.reindex()
    graph_path = tmp_path / "private" / "derived" / "symbolic_graph.json"
    raw: object = json.loads(graph_path.read_text(encoding="utf-8"))

    assert isinstance(raw, dict)
    assert raw["schema"] == "NuSelfSymbolicGraph/v1"
    nodes = cast(list[object], raw["nodes"])
    edges = cast(list[object], raw["edges"])
    assert isinstance(nodes, list)
    assert isinstance(edges, list)
    assert {node["id"] for node in nodes if isinstance(node, dict)} == {source.id, target.id}
    assert edges == [
        {
            "confidence": source.confidence,
            "id": f"{source.id}:related_to:{target.id}",
            "payload": {
                "confidence_policy": "inherits_source",
                "inverse_relation": "related_to",
                "retrieval_rule": "include_direct_neighbors",
                "symmetric": True,
                "target_exists": True,
                "temporal_policy": "independent",
                "transitive": False,
            },
            "relation": "related_to",
            "source": source.id,
            "source_refs": [source.id, target.id],
            "target": target.id,
        }
    ]

    belief_nodes = repo.list_graph_nodes()
    related_edges = repo.list_graph_edges()

    assert {node.id for node in belief_nodes} == {source.id, target.id}
    assert related_edges[0].id == f"{source.id}:related_to:{target.id}"
    assert related_edges[0].relation == "related_to"


def test_default_relation_descriptor_registry_exposes_built_ins() -> None:
    registry = default_relation_descriptor_registry()
    supersedes = registry.require("supersedes")
    related_to = registry.require("related_to")

    assert registry.names() == ("related_to", "supersedes")
    assert supersedes.inverse == "superseded_by"
    assert supersedes.retrieval_rule == "include_both_current_and_superseded"
    assert related_to.symmetric is True
    assert related_to.inverse == "related_to"


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


def test_default_registry_validates_goal_and_concept_memory_objects() -> None:
    registry = default_memory_type_registry()
    goal = MemoryObject(
        type="goal",
        payload={
            "title": "Finish memory system",
            "body": "Complete the candidate, evidence, stats, and descriptor slices.",
            "tags": ["memory"],
            "revisit_at": None,
        },
    )
    concept = MemoryObject(
        type="concept",
        payload={
            "title": "Temporal memory",
            "body": "Memory that preserves when a thought was observed and how it changes over time.",
            "tags": ["memory"],
            "revisit_at": None,
        },
    )

    registry.validate(goal)
    registry.validate(concept)

    assert registry.summarize(goal).startswith("Finish memory system:")
    assert registry.summarize(concept).startswith("Temporal memory:")


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
