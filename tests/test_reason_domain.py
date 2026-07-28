"""Tests for reason domain models."""

from __future__ import annotations

import pytest

from nuself.reason.domain import ReasoningStep, ReasoningThread


def test_thread_defaults() -> None:
    t = ReasoningThread(topic="What is the meaning of life?")
    assert t.status == "active"
    assert t.priority == "normal"
    assert t.topic == "What is the meaning of life?"
    assert t.active_items == []
    assert t.pending_items == []
    assert t.evidence_refs == []


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
