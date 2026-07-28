"""Tests for immutable Memory read-model collection ownership."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEntry,
    MemoryEvidence,
    MemoryObject,
)


def test_memory_entry_detaches_and_freezes_nested_inputs() -> None:
    tags = ["architecture"]
    related = ["mem_two"]
    relations = {"related_to": related}
    evidence = [
        MemoryEvidence(
            source_type="thread",
            source_ref="thread:default:0-1",
        )
    ]
    payload: dict[str, object] = {
        "details": {"scores": [1]},
    }
    entry = MemoryEntry(
        type="belief",
        title="Owned state",
        body="Memory entries own their containers.",
        tags=tags,
        relations=relations,
        evidence=evidence,
        payload=payload,
    )

    tags.append("changed")
    related.append("mem_three")
    evidence.clear()
    details = cast(dict[str, object], payload["details"])
    cast(list[object], details["scores"]).append(2)

    assert entry.tags == ("architecture",)
    assert entry.relations["related_to"] == ("mem_two",)
    assert len(entry.evidence) == 1
    frozen_details = entry.payload["details"]
    assert isinstance(frozen_details, Mapping)
    assert frozen_details["scores"] == (1,)
    with pytest.raises(TypeError):
        cast(dict[str, object], entry.relations)["changed"] = ("mem_four",)


def test_memory_entry_to_wire_returns_detached_mutable_containers() -> None:
    entry = MemoryEntry(
        type="belief",
        title="Detached wire",
        body="Wire records do not alias models.",
        tags=["memory"],
        relations={"related_to": ["mem_two"]},
        payload={"details": {"scores": [1]}},
    )

    wire = entry.to_wire()
    tags = wire["tags"]
    assert isinstance(tags, list)
    cast(list[object], tags).append("changed")
    relations = wire["relations"]
    assert isinstance(relations, dict)
    related = cast(dict[str, object], relations)["related_to"]
    assert isinstance(related, list)
    cast(list[object], related).append("mem_three")
    payload = wire["payload"]
    assert isinstance(payload, dict)
    details = cast(dict[str, object], payload)["details"]
    assert isinstance(details, dict)
    scores = cast(dict[str, object], details)["scores"]
    assert isinstance(scores, list)
    cast(list[object], scores).append(2)

    later = entry.to_wire()
    assert later["tags"] == ["memory"]
    assert later["relations"] == {"related_to": ["mem_two"]}
    assert later["payload"] == {"details": {"scores": [1]}}
    assert MemoryEntry.from_wire(later) == entry


def test_candidate_and_open_memory_object_own_collections() -> None:
    candidate_tags = ["candidate"]
    candidate = MemoryCandidate(
        type="goal",
        title="Candidate",
        body="Review this goal.",
        tags=candidate_tags,
        relations={"depends_on": ["mem_one"]},
    )
    payload: dict[str, object] = {
        "title": "Open memory",
        "body": "Descriptor-backed.",
        "tags": ["open"],
    }
    metadata: dict[str, object] = {"routing": {"markers": ["memory"]}}
    source_refs = ["thread:default:0-1"]
    memory = MemoryObject(
        type="belief",
        payload=payload,
        metadata=metadata,
        source_refs=source_refs,
    )

    candidate_tags.append("changed")
    cast(list[object], payload["tags"]).append("changed")
    routing = cast(dict[str, object], metadata["routing"])
    cast(list[object], routing["markers"]).append("changed")
    source_refs.append("thread:default:1-2")

    assert candidate.tags == ("candidate",)
    assert candidate.relations["depends_on"] == ("mem_one",)
    assert memory.payload["tags"] == ("open",)
    frozen_routing = memory.metadata["routing"]
    assert isinstance(frozen_routing, Mapping)
    assert frozen_routing["markers"] == ("memory",)
    assert memory.source_refs == ("thread:default:0-1",)

    wire = memory.to_wire()
    assert wire["payload"] == {
        "title": "Open memory",
        "body": "Descriptor-backed.",
        "tags": ["open"],
    }
    assert MemoryObject.from_wire(wire) == memory
