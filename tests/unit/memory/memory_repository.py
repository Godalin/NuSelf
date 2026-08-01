from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from pathlib import Path
from typing import cast

import pytest

from nuself.domain.memory import (
    MemoryEntry,
    MemoryObject,
    MemoryValidationError,
    default_memory_type_registry,
    default_relation_descriptor_registry,
)
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository, MemoryRelationFilters
from nuself.memory.repository import MemorySearchFilters, MemoryStats, memory_stats
from nuself.logs import read_log_events
from nuself.storage import auto_backend


def test_memory_repository_crud(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
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

    assert repo.get(entry.id).title == "Clarity matters most"

    repo.delete(entry.id)
    assert repo.list() == []


def test_memory_repository_isolates_and_reports_corrupt_neighbor(
    tmp_path: Path,
) -> None:
    backend = auto_backend(tmp_path / "private")
    repo = memory_entry_repository(tmp_path, backend=backend)
    healthy = repo.save(
        MemoryEntry(type="concept", title="Healthy", body="Readable")
    )
    backend.collection("memory_entries").put(
        "mem_corrupt",
        {"id": "mem_corrupt", "body": "private contents"},
    )

    assert [entry.id for entry in repo.list()] == [healthy.id]
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": "mem_corrupt",
    }
    assert "private contents" not in str(event.to_record())
    with pytest.raises((ValueError, KeyError)):
        repo.get("mem_corrupt")


def test_memory_repository_lists_relations(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
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
            relations={"supersedes": [old.id], "related_to": [related.id]},
        )
    )

    related_records = repo.list_relations(MemoryRelationFilters(relation="related_to"))

    assert len(related_records) == 1
    assert related_records[0].source_id == current.id
    assert related_records[0].target_id == related.id
    assert related_records[0].relation == "related_to"
    assert related_records[0].symmetric is True
    assert related_records[0].inverse_relation == "related_to"


def test_memory_repository_graph_nodes_and_edges(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
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
            relations={"related_to": [target.id]},
        )
    )

    belief_nodes = repo.list_graph_nodes()
    related_edges = repo.list_graph_edges()
    search_result = repo.search_graph("rebuildable")

    assert {node.id for node in belief_nodes} == {source.id, target.id}
    assert related_edges[0].id == f"{source.id}:related_to:{target.id}"
    assert related_edges[0].relation == "related_to"
    assert [node.id for node in search_result.nodes] == [target.id, source.id]
    assert [edge.id for edge in search_result.edges] == [f"{source.id}:related_to:{target.id}"]


def test_memory_repository_search_graph_supports_depth(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    a = repo.save(MemoryEntry(type="belief", title="Start node", body="Beginning."))
    b = repo.save(MemoryEntry(type="belief", title="Middle node", body="Connected."))
    c = repo.save(MemoryEntry(type="belief", title="End node", body="Distant."))
    # Chain a -> b -> c via related_to
    repo.save(MemoryEntry(type="belief", title="Start node", body="Beginning.", id=a.id, relations={"related_to": [b.id]}))
    repo.save(MemoryEntry(type="belief", title="Middle node", body="Connected.", id=b.id, relations={"related_to": [c.id]}))
    depth0 = repo.search_graph("Start", depth=0)
    depth1 = repo.search_graph("Start", depth=1)
    depth2 = repo.search_graph("Start", depth=2)

    assert [node.id for node in depth0.nodes] == [a.id]
    assert [node.id for node in depth1.nodes] == [a.id, b.id]
    assert {node.id for node in depth2.nodes} == {a.id, b.id, c.id}


def test_memory_repository_find_path(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    a = repo.save(MemoryEntry(type="belief", title="A", body="Node A."))
    b = repo.save(MemoryEntry(type="belief", title="B", body="Node B."))
    c = repo.save(MemoryEntry(type="belief", title="C", body="Node C."))
    repo.save(MemoryEntry(type="belief", title="A", body="Node A.", id=a.id, relations={"related_to": [b.id]}))
    repo.save(MemoryEntry(type="belief", title="B", body="Node B.", id=b.id, relations={"related_to": [c.id]}))
    path_ac = repo.find_path(a.id, c.id)
    path_ca = repo.find_path(c.id, a.id)
    path_none = repo.find_path(a.id, "nonexistent")

    assert len(path_ac) == 2
    assert path_ac[0].relation == "related_to"
    assert path_ac[1].relation == "related_to"
    assert len(path_ca) == 2
    assert len(path_none) == 0


def test_memory_repository_transitive_closure(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    a = repo.save(MemoryEntry(type="goal", title="A", body="Goal A."))
    b = repo.save(MemoryEntry(type="goal", title="B", body="Goal B."))
    c = repo.save(MemoryEntry(type="goal", title="C", body="Goal C."))
    d = repo.save(MemoryEntry(type="goal", title="D", body="Goal D."))
    repo.save(MemoryEntry(type="goal", title="A", body="Goal A.", id=a.id, relations={"depends_on": [b.id]}))
    repo.save(MemoryEntry(type="goal", title="B", body="Goal B.", id=b.id, relations={"depends_on": [c.id]}))
    repo.save(MemoryEntry(type="goal", title="C", body="Goal C.", id=c.id, relations={"depends_on": [d.id]}))
    closure_a = repo.transitive_closure(a.id, "depends_on")
    closure_c = repo.transitive_closure(c.id, "depends_on")

    assert {node.id for node in closure_a.nodes} == {a.id, b.id, c.id, d.id}
    assert {node.id for node in closure_c.nodes} == {c.id, d.id}
    assert len(closure_a.edges) == 3


def test_default_relation_descriptor_registry_exposes_built_ins() -> None:
    registry = default_relation_descriptor_registry()
    supersedes = registry.require("supersedes")
    related_to = registry.require("related_to")

    assert registry.names() == ("contradicts", "depends_on", "refines", "related_to", "supersedes", "supports")
    assert supersedes.inverse == "superseded_by"
    assert supersedes.retrieval_rule == "include_both_current_and_superseded"
    assert related_to.symmetric is True
    assert related_to.inverse == "related_to"


def test_memory_repository_missing_entry(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)

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


def test_memory_entry_wire_uses_only_canonical_relations() -> None:
    entry = MemoryEntry(
        type="belief",
        title="Canonical relations",
        body="Relations have one wire representation.",
        relations={
            "supersedes": ["mem_old"],
            "related_to": ["mem_peer"],
        },
    )

    wire = entry.to_wire()
    payload = entry.to_memory_object().payload

    assert wire["relations"] == {
        "supersedes": ["mem_old"],
        "related_to": ["mem_peer"],
    }
    assert "supersedes" not in wire
    assert "related_memory_ids" not in wire
    assert "supersedes" not in payload
    assert "related_memory_ids" not in payload


@pytest.mark.parametrize("field_name", ["supersedes", "related_memory_ids"])
def test_memory_entry_rejects_obsolete_relation_fields(
    field_name: str,
) -> None:
    wire = MemoryEntry(
        type="belief",
        title="Canonical relations",
        body="Relations have one wire representation.",
    ).to_wire()
    wire[field_name] = ["mem_old"]

    with pytest.raises(ValueError, match="obsolete memory relation"):
        MemoryEntry.from_wire(wire)


@pytest.mark.parametrize("importance", [0.0, 0.9, 1.0])
def test_memory_entry_importance_roundtrip(
    tmp_path: Path,
    importance: float,
) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Importance test",
            body="This entry has custom importance.",
            importance=importance,
        )
    )
    loaded = repo.get(entry.id)
    assert loaded.importance == importance

    wire = entry.to_wire()
    assert wire["importance"] == importance
    restored = MemoryEntry.from_wire(wire)
    assert restored.importance == importance


def test_memory_entry_importance_defaults_only_when_missing() -> None:
    wire = MemoryEntry(
        type="belief",
        title="Importance default",
        body="Missing importance uses the schema default.",
    ).to_wire()
    del wire["importance"]

    assert MemoryEntry.from_wire(wire).importance == 0.5

    wire["importance"] = True
    with pytest.raises(ValueError, match="number"):
        MemoryEntry.from_wire(wire)


def test_registry_importance_delegates_and_fallbacks() -> None:
    registry = default_memory_type_registry()
    memory = MemoryObject(
        type="belief",
        payload={"title": "Test", "body": "Body", "tags": []},
        importance=0.75,
    )
    assert registry.importance(memory) == 0.75

    unknown = MemoryObject(
        type="unknown_type",
        payload={"title": "Test", "body": "Body", "tags": []},
        importance=0.33,
        review_state="draft",
    )
    assert registry.importance(unknown) == 0.33


def test_registry_importance_uses_type_default_when_unset() -> None:
    registry = default_memory_type_registry()
    # MemoryObject default importance is 1.0; descriptor should substitute type default.
    profile_fact = MemoryObject(
        type="profile_fact",
        payload={"title": "Test", "body": "Body", "tags": []},
    )
    assert registry.importance(profile_fact) == 0.9

    open_question = MemoryObject(
        type="open_question",
        payload={"title": "Test", "body": "Body", "tags": []},
    )
    assert registry.importance(open_question) == 0.3

    # Explicit importance overrides the default.
    explicit = MemoryObject(
        type="profile_fact",
        payload={"title": "Test", "body": "Body", "tags": []},
        importance=0.5,
    )
    assert registry.importance(explicit) == 0.5


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
    repo = memory_entry_repository(tmp_path)
    invalid = MemoryEntry(type="belief", title="", body="Missing title.")

    try:
        repo.save(invalid)
    except MemoryValidationError as exc:
        assert exc.memory_type == "belief"
        assert exc.issues[0].field == "payload.title"
        return
    raise AssertionError("expected MemoryValidationError")


def test_repository_quarantines_unknown_draft_type(tmp_path: Path) -> None:
    from nuself.domain.memory import MemoryEntryType
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(MemoryEntry(type=cast(MemoryEntryType, "truly_unknown_type"), title="Concise style", body="Keep summaries compact."))

    assert repo.get(entry.id).title == "Concise style"
    assert repo.get(entry.id).review_state == "quarantined"


def test_repository_rejects_unknown_non_draft_type(tmp_path: Path) -> None:
    from nuself.domain.memory import MemoryEntryType
    repo = memory_entry_repository(tmp_path)
    invalid = MemoryEntry(type=cast(MemoryEntryType, "truly_unknown_type"), title="Concise style", body="Keep summaries compact.", review_state="reviewed")

    try:
        repo.save(invalid)
    except MemoryValidationError as exc:
        assert exc.memory_type == "truly_unknown_type"
        return
    raise AssertionError("expected MemoryValidationError")


def test_memory_repository_search_filters_and_stats(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
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
    stats = memory_stats(
        repo,
        memory_candidate_repository(tmp_path),
    )

    assert [entry.title for entry in filtered] == ["Temporal memory"]
    assert stats.entries_total == 2
    assert stats.entries_by_type == {"belief": 1, "episode": 1}
    assert stats.entries_by_review_state["reviewed"] == 1
    assert stats.entries_with_observed_at == 1


def test_memory_stats_detaches_and_freezes_mapping_inputs() -> None:
    entries_by_type = {"belief": 1}
    averages = {"belief": 0.75}
    stats = MemoryStats(
        entries_total=1,
        candidates_total=0,
        entries_by_type=entries_by_type,
        avg_importance_by_type=averages,
    )

    entries_by_type["episode"] = 1
    averages["belief"] = 0.1

    assert stats.entries_by_type == {"belief": 1}
    assert stats.avg_importance_by_type == {"belief": 0.75}
    with pytest.raises(TypeError):
        cast(dict[str, int], stats.entries_by_type)["goal"] = 1


def test_registry_merge_prefers_incoming_payload_and_preserves_metadata() -> None:
    registry = default_memory_type_registry()
    existing = MemoryObject(
        type="belief",
        payload={"title": "Old", "body": "Old body.", "tags": ["a", "b"]},
        confidence=0.5,
        source_refs=["ref1"],
        review_state="draft",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    incoming = MemoryObject(
        type="belief",
        payload={"title": "New", "body": "New body.", "tags": ["b", "c"]},
        confidence=0.9,
        source_refs=["ref2"],
        review_state="reviewed",
        created_at="2026-02-01T00:00:00+00:00",
        updated_at="2026-02-01T00:00:00+00:00",
    )

    merged = registry.merge(existing, incoming)

    assert merged.id == existing.id
    assert merged.type == "belief"
    assert merged.payload["title"] == "New"
    assert merged.payload["body"] == "New body."
    assert merged.payload["tags"] == ("a", "b", "c")
    assert merged.confidence == 0.9
    assert merged.source_refs == ("ref1", "ref2")
    assert merged.review_state == "reviewed"
    assert merged.created_at == existing.created_at
    assert merged.updated_at == incoming.updated_at


def test_registry_conflicts_detects_matching_titles() -> None:
    registry = default_memory_type_registry()
    a = MemoryObject(type="belief", payload={"title": "Same Title", "body": "A"})
    b = MemoryObject(type="belief", payload={"title": "Same Title", "body": "B"})
    c = MemoryObject(type="belief", payload={"title": "Different", "body": "C"})

    assert registry.conflicts(a, b) is True
    assert registry.conflicts(a, c) is False


def test_registry_conflicts_same_id_always_true() -> None:
    registry = default_memory_type_registry()
    obj = MemoryObject(type="belief", payload={"title": "X", "body": "Y"}, id="same-id")

    assert registry.conflicts(obj, obj) is True


def test_registry_decay_returns_memory_unchanged() -> None:
    registry = default_memory_type_registry()
    memory = MemoryObject(type="belief", payload={"title": "T", "body": "B"})

    result = registry.decay(memory, "2026-05-08T00:00:00+00:00")

    assert result is memory


def test_registry_retrieve_defaults_to_true() -> None:
    registry = default_memory_type_registry()

    assert registry.retrieve("belief", "any query", 10) is True


def test_registry_reflect_defaults_to_empty() -> None:
    registry = default_memory_type_registry()
    memory = MemoryObject(type="belief", payload={"title": "T", "body": "B"})

    assert registry.reflect(memory, "some context") == []


def test_persona_descriptor_conflicts_by_persona_id() -> None:
    registry = default_memory_type_registry()
    a = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "analyst", "description": "A"},
    )
    b = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "analyst", "description": "B"},
    )
    c = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "builder", "description": "C"},
    )

    assert registry.conflicts(a, b) is True
    assert registry.conflicts(a, c) is False


def test_unknown_type_uses_default_merge_and_conflicts() -> None:
    registry = default_memory_type_registry()
    existing = MemoryObject(
        type="unknown_type",
        payload={"key": "old"},
        id="mem-1",
        created_at="2026-01-01T00:00:00+00:00",
    )
    incoming = MemoryObject(
        type="unknown_type",
        payload={"key": "new"},
        created_at="2026-02-01T00:00:00+00:00",
    )

    merged = registry.merge(existing, incoming)
    assert merged.payload["key"] == "new"
    assert merged.id == "mem-1"

    a = MemoryObject(type="unknown_type", payload={}, id="x")
    b = MemoryObject(type="unknown_type", payload={}, id="y")
    assert registry.conflicts(a, b) is False
    assert registry.conflicts(a, a) is True

    assert registry.decay(existing, "now") is existing
    assert registry.retrieve("unknown_type", "q", 5) is True
    assert registry.reflect(existing, "ctx") == []


def test_registry_describe_returns_description_for_known_types() -> None:
    registry = default_memory_type_registry()
    assert registry.describe("belief") == "a claim or stance"
    assert registry.describe("persona_instruction") == "persona instruction memory"


def test_registry_describe_returns_unknown_for_missing_types() -> None:
    registry = default_memory_type_registry()
    assert registry.describe("nonexistent") == "unknown type"


def test_registry_example_returns_example_object() -> None:
    registry = default_memory_type_registry()
    example = registry.example("belief")
    assert example is not None
    assert example.type == "belief"
    assert example.payload["title"] == "Example belief"


def test_registry_example_returns_none_for_unknown_type() -> None:
    registry = default_memory_type_registry()
    assert registry.example("unknown") is None
