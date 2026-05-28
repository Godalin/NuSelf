"""Tests for ReasonAdvancer."""

from __future__ import annotations

from nuself.reason.advancer import REASON_ADVANCE_SYSTEM_PROMPT, build_advance_prompt, build_system_prompt, step_from_data
from nuself.reason.domain import ReasoningThread


def test_build_prompt_includes_thread_fields() -> None:
    thread = ReasoningThread(
        topic="Test question",
        working_summary="Some summary",
        evidence_refs=["ref1"],
        active_items_data=({"label": "hyp1", "kind": "finding"},),
        pending_items_data=({"label": "q1", "kind": "pending"},),
    )
    prompt = build_advance_prompt(thread)
    assert "Test question" in prompt
    assert "Some summary" in prompt
    assert "hyp1" in prompt
    assert "q1" in prompt
    assert "ref1" in prompt
    assert "at most one complete round" in prompt


def test_build_prompt_empty_lists_omitted() -> None:
    thread = ReasoningThread(topic="Q")
    prompt = build_advance_prompt(thread)
    assert "Active items:" not in prompt
    assert "Pending items:" not in prompt
    assert "Evidence references:" not in prompt


def test_build_system_prompt_keeps_invariant_contract_with_generated_prompt() -> None:
    thread = ReasoningThread(topic="Q", reasoning_prompt="Move one debate turn at a time.")

    prompt = build_system_prompt(thread)

    assert REASON_ADVANCE_SYSTEM_PROMPT in prompt
    assert "Move one debate turn at a time." in prompt
    assert "ReasonStepOutput" in prompt
    assert "at most one complete round" in prompt
    assert "call persona_think for that persona" in prompt
    assert "do not fabricate later persona speech" in prompt
    assert "terminal_status=suggest_resolved" in prompt
    assert "Do not rely on prose alone to signal completion" in prompt


def teststep_from_data_accepts_valid() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "terminal_status": "suggest_resolved",
        "terminal_reason": "done",
    }
    step = step_from_data(data, "test-thread")
    assert step is not None
    assert step.id is not None
    assert step.thread_id == "test-thread"
    assert step.summary == "s"
    assert step.delta == "d"
    assert step.kind == "progress"
    assert step.output == "out"
    assert step.terminal_status == "suggest_resolved"
    assert step.terminal_reason == "done"


def teststep_from_data_defaults_invalid_terminal_status_to_continue() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "terminal_status": "done",
    }

    step = step_from_data(data, "test-thread")

    assert step is not None
    assert step.terminal_status == "continue"


def teststep_from_data_filters_non_string_evidence_refs() -> None:
    data: dict[str, object] = {
        "summary": "s",
        "delta": "d",
        "kind": "progress",
        "output": "out",
        "evidence_refs": ["mem_1", 3, None],
    }
    step = step_from_data(data, "test-thread")

    assert step is not None
    assert step.evidence_refs == ["mem_1"]


def teststep_from_data_rejects_missing_fields() -> None:
    assert step_from_data({"kind": "progress"}, "t") is None  # type: ignore[reportArgumentType]
    assert step_from_data({"summary": "s", "delta": "d"}, "t") is None  # type: ignore[reportArgumentType]
    assert step_from_data({"summary": "s", "delta": "d", "kind": "progress"}, "t") is None  # type: ignore[reportArgumentType]


def teststep_from_data_rejects_invalid_kind() -> None:
    assert step_from_data({"summary": "s", "delta": "d", "kind": "invalid", "output": "out"}, "t") is None  # type: ignore[reportArgumentType]
