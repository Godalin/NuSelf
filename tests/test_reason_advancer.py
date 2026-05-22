"""Tests for ReasonAdvancer."""

from __future__ import annotations

from nuself.llm import ChatLLM, ChatMessage
from nuself.reason.advancer import ReasonAdvancer, _build_advance_prompt, _parse_step_json, _step_from_data
from nuself.reason.domain import ReasoningThread


def test_build_prompt_includes_thread_fields() -> None:
    thread = ReasoningThread(
        question="Test question",
        working_summary="Some summary",
        hypotheses=["hyp1"],
        open_questions=["q1"],
        evidence_refs=["ref1"],
    )
    prompt = _build_advance_prompt(thread)
    assert "Test question" in prompt
    assert "Some summary" in prompt
    assert "hyp1" in prompt
    assert "q1" in prompt
    assert "ref1" in prompt


def test_build_prompt_empty_lists_omitted() -> None:
    thread = ReasoningThread(question="Q")
    prompt = _build_advance_prompt(thread)
    assert "Hypotheses:" not in prompt
    assert "Open questions:" not in prompt
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
    thread = ReasoningThread(question="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "progress", "new_hypotheses": ["h1"], "new_open_questions": ["q1"], "evidence_refs": ["e1"], "confidence": 0.9}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.summary == "s"
    assert step.kind == "progress"
    assert step.new_hypotheses == ["h1"]
    assert step.new_open_questions == ["q1"]
    assert step.evidence_refs == ["e1"]
    assert step.confidence == 0.9
    assert step.thread_id == thread.id


def test_advance_returns_none_on_empty_response() -> None:
    thread = ReasoningThread(question="Test")
    llm = FakeLLM("")
    advancer = ReasonAdvancer(cast_llm(llm))
    assert advancer.advance(thread) is None


def test_advance_returns_none_on_invalid_json() -> None:
    thread = ReasoningThread(question="Test")
    llm = FakeLLM("not json")
    advancer = ReasonAdvancer(cast_llm(llm))
    assert advancer.advance(thread) is None


def test_advance_confidence_clamped() -> None:
    thread = ReasoningThread(question="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "synthesis", "confidence": 2.5}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.confidence == 1.0


def test_advance_confidence_none_when_missing() -> None:
    thread = ReasoningThread(question="Test")
    llm = FakeLLM('{"summary": "s", "delta": "d", "kind": "resolution"}')
    advancer = ReasonAdvancer(cast_llm(llm))
    step = advancer.advance(thread)
    assert step is not None
    assert step.confidence is None


def cast_llm(llm: FakeLLM) -> ChatLLM:
    from typing import cast
    return cast(ChatLLM, llm)
