"""Tests for reason domain models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from nuself.reason.domain import ReasoningStep, ReasoningThread


def test_thread_defaults() -> None:
    t = ReasoningThread(topic="What is the meaning of life?")
    assert t.status == "active"
    assert t.priority == "normal"
    assert t.topic == "What is the meaning of life?"
    assert t.active_items == []
    assert t.pending_items == []
    assert t.evidence_refs == ()


def test_thread_empty_question_raises() -> None:
    try:
        ReasoningThread(topic="")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_thread_invalid_status_raises() -> None:
    try:
        ReasoningThread(topic="test", status="invalid")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_thread_to_wire_roundtrip() -> None:
    t = ReasoningThread(
        topic="Should I switch careers?",
        working_summary="Exploring options",
        evidence_refs=["mem-123"],
        priority="high",
        active_items_data=({"label": "Option A", "kind": "finding"}, {"label": "Option B", "kind": "finding"}),
        pending_items_data=({"label": "What about money?", "kind": "pending"},),
    )
    wire = t.to_wire()
    assert "question" not in wire
    t2 = ReasoningThread.from_wire(wire)
    assert t2 == t


def test_thread_detaches_and_freezes_collection_inputs() -> None:
    evidence_refs = ["mem-123"]
    active_item: dict[str, object] = {
        "label": "Option A",
        "metadata": {"scores": [1]},
    }
    thread = ReasoningThread(
        topic="Detached state",
        evidence_refs=evidence_refs,
        active_items_data=(active_item,),
    )

    evidence_refs.append("mem-456")
    metadata = active_item["metadata"]
    assert isinstance(metadata, dict)
    scores = cast(list[object], metadata["scores"])
    assert isinstance(scores, list)
    scores.append(2)

    assert thread.evidence_refs == ("mem-123",)
    frozen_metadata = thread.active_items_data[0]["metadata"]
    assert isinstance(frozen_metadata, Mapping)
    assert frozen_metadata["scores"] == (1,)
    with pytest.raises(TypeError):
        cast(dict[str, object], thread.active_items_data[0])["label"] = "changed"


def test_thread_to_wire_returns_detached_mutable_containers() -> None:
    thread = ReasoningThread(
        topic="Detached wire",
        active_items_data=(
            {"label": "Option A", "metadata": {"scores": [1]}},
        ),
    )

    wire = thread.to_wire()
    active_items = wire["active_items_data"]
    assert isinstance(active_items, list)
    first = cast(list[object], active_items)[0]
    assert isinstance(first, dict)
    first_record = cast(dict[str, object], first)
    first_record["label"] = "changed"
    metadata = first_record["metadata"]
    assert isinstance(metadata, dict)
    metadata_record = cast(dict[str, object], metadata)
    scores = metadata_record["scores"]
    assert isinstance(scores, list)
    cast(list[object], scores).append(2)

    later = thread.to_wire()
    assert later["active_items_data"] == [
        {"label": "Option A", "metadata": {"scores": [1]}}
    ]


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("created_at", "not-a-time"),
        ("updated_at", "2026-01-01T00:00:00"),
        ("last_advanced_at", 42),
        ("next_review_after", "2026-01-01T00:00:00"),
        ("skip_next_advance_until", "not-a-time"),
    ),
)
def test_thread_from_wire_rejects_invalid_timestamps(
    field_name: str,
    value: object,
) -> None:
    wire = ReasoningThread(topic="Strict timestamps").to_wire()
    wire[field_name] = value

    with pytest.raises(ValueError):
        ReasoningThread.from_wire(wire)


def test_thread_local_construction_rejects_naive_cooldown() -> None:
    with pytest.raises(ValueError, match="include a timezone"):
        ReasoningThread(
            topic="Strict cooldown",
            skip_next_advance_until="2026-01-01T00:00:00",
        )


def test_thread_with_status() -> None:
    t = ReasoningThread(topic="test").with_status("paused")
    assert t.status == "paused"
    assert t.updated_at != t.created_at


def test_step_defaults() -> None:
    s = ReasoningStep(thread_id="reason-abc", summary="Test step")
    assert s.kind == "progress"
    assert s.terminal_status == "continue"
    assert s.terminal_reason == ""
    assert s.new_findings == []
    assert s.retired_findings == []


def test_step_empty_thread_id_raises() -> None:
    try:
        ReasoningStep(thread_id="", summary="test")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_step_empty_summary_raises() -> None:
    try:
        ReasoningStep(thread_id="reason-abc", summary="")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_step_invalid_kind_raises() -> None:
    try:
        ReasoningStep(thread_id="reason-abc", kind="invalid", summary="test")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_step_to_wire_roundtrip() -> None:
    s = ReasoningStep(
        thread_id="reason-abc",
        kind="contradiction",
        summary="Found a contradiction",
        delta="New evidence contradicts hypothesis A",
        evidence_refs=["mem-456"],
        confidence=0.8,
        terminal_status="suggest_resolved",
        terminal_reason="The contradiction resolves the thread.",
        new_findings_data=({"label": "New finding", "kind": "finding"},),
        new_pending_data=({"label": "Open question", "kind": "pending"},),
    )
    wire = s.to_wire()
    s2 = ReasoningStep.from_wire(wire)
    assert s2 == s


def test_step_detaches_nested_tool_logs_and_wire_output() -> None:
    tool_log: dict[str, object] = {
        "event": "service_tool_called",
        "metadata": {"result": {"items": [1]}},
    }
    step = ReasoningStep(
        thread_id="reason-abc",
        summary="Captured a tool",
        tool_logs=(tool_log,),
    )

    metadata = tool_log["metadata"]
    assert isinstance(metadata, dict)
    result = cast(dict[str, object], metadata)["result"]
    assert isinstance(result, dict)
    items = cast(dict[str, object], result)["items"]
    assert isinstance(items, list)
    cast(list[object], items).append(2)

    frozen_metadata = step.tool_logs[0]["metadata"]
    assert isinstance(frozen_metadata, Mapping)
    frozen_result = cast(object, frozen_metadata["result"])
    assert isinstance(frozen_result, Mapping)
    assert frozen_result["items"] == (1,)

    wire = step.to_wire()
    wire_logs = wire["tool_logs"]
    assert isinstance(wire_logs, list)
    wire_log = cast(list[object], wire_logs)[0]
    assert isinstance(wire_log, dict)
    wire_metadata = cast(dict[str, object], wire_log)["metadata"]
    assert isinstance(wire_metadata, dict)
    wire_result = cast(dict[str, object], wire_metadata)["result"]
    assert isinstance(wire_result, dict)
    wire_items = cast(dict[str, object], wire_result)["items"]
    assert isinstance(wire_items, list)
    cast(list[object], wire_items).append(3)
    assert step.to_wire()["tool_logs"] == [
        {
            "event": "service_tool_called",
            "metadata": {"result": {"items": [1]}},
        }
    ]


def test_step_from_legacy_wire_defaults_terminal_status() -> None:
    s = ReasoningStep(thread_id="reason-abc", summary="Legacy step")
    wire = s.to_wire()
    del wire["terminal_status"]
    del wire["terminal_reason"]

    parsed = ReasoningStep.from_wire(wire)

    assert parsed.terminal_status == "continue"
    assert parsed.terminal_reason == ""


def test_step_invalid_terminal_status_raises() -> None:
    try:
        ReasoningStep(thread_id="reason-abc", summary="test", terminal_status="done")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError:
        pass
