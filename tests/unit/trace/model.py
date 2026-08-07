"""Tests for immutable Trace read-model collection ownership."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from nuself.trace.model import ThoughtTrace, TraceLink


def test_thought_trace_detaches_and_freezes_collection_inputs() -> None:
    inputs = ["thread:default:1:user"]
    metadata: dict[str, object] = {
        "context": {"references": ["memory:one"]},
    }
    trace = ThoughtTrace(
        kind="chat_turn",
        title="Detached trace",
        summary="Trace owns its state.",
        inputs=inputs,
        metadata=metadata,
    )

    inputs.append("thread:default:2:user")
    context = cast(dict[str, object], metadata["context"])
    references = cast(list[object], context["references"])
    references.append("memory:two")

    assert trace.inputs == ("thread:default:1:user",)
    frozen_context = trace.metadata["context"]
    assert isinstance(frozen_context, Mapping)
    assert frozen_context["references"] == ("memory:one",)
    with pytest.raises(TypeError):
        cast(dict[str, object], trace.metadata)["changed"] = True


def test_thought_trace_to_wire_returns_detached_mutable_containers() -> None:
    trace = ThoughtTrace(
        kind="decision",
        title="Detached wire",
        summary="Wire output does not alias the model.",
        inputs=["artifact:one"],
        metadata={"context": {"references": ["memory:one"]}},
    )

    wire = trace.to_wire()
    inputs = wire["inputs"]
    assert isinstance(inputs, list)
    cast(list[object], inputs).append("artifact:two")
    metadata = wire["metadata"]
    assert isinstance(metadata, dict)
    context = cast(dict[str, object], metadata)["context"]
    assert isinstance(context, dict)
    references = cast(dict[str, object], context)["references"]
    assert isinstance(references, list)
    cast(list[object], references).append("memory:two")

    assert trace.to_wire()["inputs"] == ["artifact:one"]
    assert trace.to_wire()["metadata"] == {
        "context": {"references": ["memory:one"]}
    }


def test_trace_link_detaches_metadata_and_roundtrips() -> None:
    metadata: dict[str, object] = {"weights": [1]}
    link = TraceLink(
        source_id="trace:one",
        target_id="memory:one",
        relation="supports",
        summary="Trace supports memory.",
        metadata=metadata,
    )

    cast(list[object], metadata["weights"]).append(2)
    assert link.metadata["weights"] == (1,)

    wire = link.to_wire()
    weights = cast(dict[str, object], wire["metadata"])["weights"]
    assert isinstance(weights, list)
    cast(list[object], weights).append(3)

    assert TraceLink.from_wire(link.to_wire()) == link
    assert link.to_wire()["metadata"] == {"weights": [1]}
