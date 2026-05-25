"""Tests for reason domain models."""

from __future__ import annotations

from nuself.reason.domain import ReasoningStep, ReasoningThread


def test_thread_defaults() -> None:
    t = ReasoningThread(topic="What is the meaning of life?")
    assert t.status == "active"
    assert t.priority == "normal"
    assert t.topic == "What is the meaning of life?"
    assert t.hypotheses == []
    assert t.open_questions == []
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
        hypotheses=["Option A", "Option B"],
        open_questions=["What about money?"],
        evidence_refs=["mem-123"],
        priority="high",
    )
    wire = t.to_wire()
    t2 = ReasoningThread.from_wire(wire)
    assert t2 == t


def test_thread_with_status() -> None:
    t = ReasoningThread(topic="test").with_status("paused")
    assert t.status == "paused"
    assert t.updated_at != t.created_at


def test_step_defaults() -> None:
    s = ReasoningStep(thread_id="reason-abc", summary="Test step")
    assert s.kind == "progress"
    assert s.new_hypotheses == []
    assert s.retired_hypotheses == []


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
        new_hypotheses=["Hypothesis C"],
        retired_hypotheses=["Hypothesis A"],
        new_open_questions=["What about X?"],
        evidence_refs=["mem-456"],
        confidence=0.8,
    )
    wire = s.to_wire()
    s2 = ReasoningStep.from_wire(wire)
    assert s2 == s
