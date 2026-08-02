"""Tests for immutable Profile and Source read-model collections."""

from __future__ import annotations

from typing import cast

import pytest

from nuself.memory.model import MemoryEvidence
from nuself.profile.model import ProfileItem
from nuself.source.record import SourceDocument


def test_profile_item_detaches_and_freezes_collection_inputs() -> None:
    tags = ["profile"]
    source_refs = ["source:one:0"]
    related = ["mem_one"]
    relations = {"related_to": related}
    evidence = [
        MemoryEvidence(
            source_type="source",
            source_ref="source:one:0",
        )
    ]
    item = ProfileItem(
        type="profile_fact",
        title="Owned profile",
        body="Profile records own their containers.",
        tags=tags,
        source_refs=source_refs,
        relations=relations,
        evidence=evidence,
    )

    tags.append("changed")
    source_refs.append("source:two:0")
    related.append("mem_two")
    evidence.clear()

    assert item.tags == ("profile",)
    assert item.source_refs == ("source:one:0",)
    assert item.relations["related_to"] == ("mem_one",)
    assert len(item.evidence) == 1
    with pytest.raises(TypeError):
        cast(dict[str, object], item.relations)["changed"] = ("mem_three",)


def test_profile_item_to_wire_returns_detached_mutable_containers() -> None:
    item = ProfileItem(
        type="profile_fact",
        title="Detached profile",
        body="Wire output does not alias profile state.",
        tags=["profile"],
        relations={"related_to": ["mem_one"]},
    )

    wire = item.to_wire()
    tags = wire["tags"]
    assert isinstance(tags, list)
    cast(list[object], tags).append("changed")
    relations = wire["relations"]
    assert isinstance(relations, dict)
    related = cast(dict[str, object], relations)["related_to"]
    assert isinstance(related, list)
    cast(list[object], related).append("mem_two")

    assert item.to_wire()["tags"] == ["profile"]
    assert item.to_wire()["relations"] == {"related_to": ["mem_one"]}
    assert ProfileItem.from_wire(item.to_wire()) == item


def test_source_document_detaches_tags_and_returns_detached_wire() -> None:
    tags = ["source"]
    document = SourceDocument(
        id="src_one",
        title="Owned source",
        path="/tmp/source.md",
        kind="markdown",
        tags=tags,
    )

    tags.append("changed")
    assert document.tags == ("source",)

    wire = document.to_wire()
    wire_tags = wire["tags"]
    assert isinstance(wire_tags, list)
    cast(list[object], wire_tags).append("changed")

    assert document.to_wire()["tags"] == ["source"]
    assert SourceDocument.from_wire(document.to_wire()) == document
