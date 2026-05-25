"""Tests for ReasonAdvancer."""

from __future__ import annotations

from nuself.llm import ChatLLM, ChatMessage
from nuself.reason.advancer import ReasonAdvancer, _build_advance_prompt, _parse_step_json, _step_from_data
from nuself.reason.domain import ReasoningThread


def test_build_prompt_includes_thread_fields() -> None:
    thread = ReasoningThread(
        topic="Test question",
        working_summary="Some summary",
        evidence_refs=["ref1"],
        active_items_data=({"label": "hyp1", "kind": "finding"},),
        pending_items_data=({"label": "q1", "kind": "pending"},),
    )
    prompt = _build_advance_prompt(thread)
    assert "Test question" in prompt
    assert "Some summary" in prompt
    assert "hyp1" in prompt
    assert "q1" in prompt
    assert "ref1" in prompt


def test_build_prompt_empty_lists_omitted() -> None:
    thread = ReasoningThread(topic="Q")
    prompt = _build_advance_prompt(thread)
    assert "Active items:" not in prompt
    assert "Pending items:" not in prompt
    assert "Evidence references:" not in prompt


def test_parse_valid_json() -> None:
    raw = '{"summary": "s", "delta": "d", "kind": "progress", "confidence": 0.8}'
    result = _parse_step_json(raw)
    assert result is not None
    assert result["summary"] == "s"
    assert result["kind"] == "progress"


def test_parse_json_with_triple_backtick_fence() -> None:
    raw = '```\n{"summary": "s", "delta": "d", "kind": "no_change", "confidence": 0.5}\n```'
    result = _parse_step_json(raw)
    assert result is not None
    assert result["summary"] == "s"


def test_parse_invalid_json_returns_none() -> None:
    assert _parse_step_json("not json") is None
    assert _parse_step_json("") is None
    assert _parse_step_json('"just a string"') is None


def test_step_from_data_accepts_valid() -> None:
    data = {"summary": "s", "delta": "d", "kind": "progress"}
    step = _step_from_data(data, "test-thread")
    assert step is not None
    assert step.id is not None
    assert step.thread_id == "test-thread"
    assert step.summary == "s"
    assert step.delta == "d"
    assert step.kind == "progress"


def test_step_from_data_rejects_missing_fields() -> None:
    assert _step_from_data({"kind": "progress"}, "t") is None
    assert _step_from_data({"summary": "s", "delta": "d"}, "t") is None


def test_step_from_data_rejects_invalid_kind() -> None:
    assert _step_from_data({"summary": "s", "delta": "d", "kind": "invalid"}, "t") is None


class FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages: list[ChatMessage]) -> str:
        return self._response


def test_advance_returns_step_on_valid_llm() -> None:
    thread = ReasoningThread(topic="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "progress", "evidence_refs": ["e1"], "confidence": 0.9, "new_findings": [{"label": "f1", "kind": "finding"}], "new_pending": [{"label": "p1", "kind": "pending"}], "retired_findings": [{"label": "old"}], "next_steps": [{"label": "n1"}]}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.summary == "s"
    assert step.kind == "progress"
    assert step.evidence_refs == ["e1"]
    assert step.confidence == 0.9
    assert step.thread_id == thread.id
    assert len(step.new_findings) == 1
    assert step.new_findings[0].label == "f1"
    assert len(step.new_pending) == 1
    assert step.new_pending[0].label == "p1"
    assert len(step.retired_findings) == 1
    assert step.retired_findings[0].label == "old"
    assert len(step.next_steps) == 1
    assert step.next_steps[0].label == "n1"


def test_advance_returns_none_on_empty_response() -> None:
    thread = ReasoningThread(topic="Test")
    llm = FakeLLM("")
    advancer = ReasonAdvancer(cast_llm(llm))
    assert advancer.advance(thread) is None


def test_advance_returns_none_on_invalid_json() -> None:
    thread = ReasoningThread(topic="Test")
    llm = FakeLLM("not json")
    advancer = ReasonAdvancer(cast_llm(llm))
    assert advancer.advance(thread) is None


def test_advance_confidence_clamped() -> None:
    thread = ReasoningThread(topic="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "synthesis", "confidence": 2.5}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.confidence == 1.0


def test_advance_confidence_none_when_missing() -> None:
    thread = ReasoningThread(topic="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "resolution"}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.confidence is None


def cast_llm(llm: FakeLLM) -> ChatLLM:
    from typing import cast
    return cast(ChatLLM, llm)
