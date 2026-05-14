# pyright: reportPrivateUsage=false
"""Tests for competitive proactive persona discussion."""

from __future__ import annotations

import json

import pytest

from nuself.agent.persona import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    HISTORIAN_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaDefinition,
    PersonaInput,
    PersonaSynthesis,
    PersonaTurnState,
)
from nuself.domain.proactive import IdeaCandidate
from nuself.llm import ChatMessage
from nuself.proactive_persona import (
    LLMBackedScoringPersonaNode,
    PersonaCompetitionResult,
    ProactivePersonaDiscussion,
)


class _FakePersonaDriver:
    def run(self, turn_state: PersonaTurnState) -> PersonaTurnState:
        contributions: list[PersonaContribution] = []
        notes: list[str] = []
        for persona in turn_state.selected_personas:
            note = f"{persona.id}|{turn_state.input.memory_context}"
            contributions.append(PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0))
            notes.append(note)
        return PersonaTurnState(
            input=turn_state.input,
            selected_personas=turn_state.selected_personas,
            contributions=tuple(contributions),
            synthesis=PersonaSynthesis(
                summary=" | ".join(notes),
                source_personas=tuple(p.id for p in turn_state.selected_personas),
                confidence=0.0,
            ),
        )


class _FakeLLM:
    """Multi-purpose fake LLM that returns different JSON based on prompt content."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        content = messages[0].content
        if "Discussion Host" in content:
            return self._responses.get("select", '{"selected_persona_ids": ["analyst_self", "skeptic_self"], "reason": "test"}')
        if "score" in content and "note" in content:
            return self._responses.get("score", '{"note": "test note", "score": 0.6}')
        if "moderator" in content:
            return self._responses.get("moderator", '{"converged": false, "emergent_persona": "none", "reason": "test"}')
        return '{"note": "fallback", "score": 0.5}'


def _make_candidate(
    body: str = "Test body",
    candidate_type: str = "question",
    confidence: float = 0.8,
    novelty: float = 0.8,
    urgency: float = 0.5,
    interruption_cost: float = 0.2,
) -> IdeaCandidate:
    return IdeaCandidate(
        id="c1",
        title="Test",
        body=body,
        candidate_type=candidate_type,  # type: ignore[arg-type]
        confidence=confidence,
        novelty=novelty,
        urgency=urgency,
        interruption_cost=interruption_cost,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )


# --- No-LLM fallback tests ---


def test_discuss_approves_strong_candidate() -> None:
    discussion = ProactivePersonaDiscussion(min_participants=2, max_participants=4)
    candidate = _make_candidate(confidence=0.9, novelty=0.9, interruption_cost=0.1)
    result = discussion.discuss(candidate)
    assert isinstance(result, PersonaCompetitionResult)
    assert result.approved is True
    assert result.scores
    assert result.reason.startswith("approved after ")


def test_select_personas_with_llm_fallback_without_llm() -> None:
    personas = (ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA, HISTORIAN_PERSONA)
    discussion = ProactivePersonaDiscussion(personas=personas, min_participants=2, max_participants=3)
    selected = discussion._select_personas_with_llm(_make_candidate())
    assert 2 <= len(selected) <= 3
    assert all(p.id != "synthesizer_self" for p in selected)


def test_blocking_veto_with_weak_support() -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(SKEPTIC_PERSONA, ANALYST_PERSONA),
        min_participants=2,
        max_participants=2,
        blocking_threshold=0.5,
        override_threshold=0.9,
        composite_threshold=0.1,
    )
    candidate = _make_candidate(confidence=0.1, novelty=0.1, interruption_cost=0.9)
    result = discussion.discuss(candidate)
    # Without LLM, all scores are 0.5 (fallback). 0.5 is not below blocking_threshold=0.5,
    # so no blocking veto. Composite 0.5 >= 0.1, so approved.
    assert result.approved is True


def test_discuss_shares_context_across_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
        min_participants=2,
        max_participants=2,
        max_turns=3,
        consensus_spread_threshold=0.0,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    candidate = _make_candidate(body="A shared context should evolve during debate.")

    result = discussion.discuss(candidate)

    assert result.approved is True
    assert any(line.startswith("host:") for line in result.discussion_trace)
    assert any("moderator_self" in line for line in result.discussion_trace)
    assert any(line.startswith("turn-1:") for line in result.discussion_trace)
    assert any(line.startswith("turn-2:") for line in result.discussion_trace)
    assert any(line.startswith("turn-3:") for line in result.discussion_trace)
    assert any(line.startswith("turn-2:") and "turn-1:" in line for line in result.discussion_trace)
    assert any(line.startswith("turn-3:") and "turn-2:" in line for line in result.discussion_trace)


def test_discuss_spawns_emergent_temporary_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA),
        min_participants=2,
        max_participants=2,
        max_turns=2,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        discussion,
        "_moderator_judgment",
        _spawn_bridge_judgment,
    )
    candidate = _make_candidate(
        candidate_type="connection",
        confidence=0.9,
        novelty=0.9,
        interruption_cost=0.2,
    )

    result = discussion.discuss(candidate)

    assert result.approved is True
    assert result.emergent_persona_ids == ("bridge_self",)
    assert any("bridge_self" in line for line in result.discussion_trace)


# --- LLM-driven tests ---


def test_llm_backed_scoring_persona_node_parses_note_and_score() -> None:
    class _ScoringLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return '{"note": "This is a strong idea.", "score": 0.85}'

    node = LLMBackedScoringPersonaNode(_ScoringLLM())
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test candidate"))

    assert result.notes == ("This is a strong idea.",)
    assert result.confidence == 0.85


def test_llm_backed_scoring_persona_node_fallback_on_bad_json() -> None:
    class _BadJsonLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return "not json"

    node = LLMBackedScoringPersonaNode(_BadJsonLLM())
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test"))

    assert result.notes == ("analyst_self considered the topic.",)
    assert result.confidence == 0.5


def test_llm_backed_scoring_persona_node_clamps_score() -> None:
    class _OverflowLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return '{"note": "Overflow", "score": 1.5}'

    node = LLMBackedScoringPersonaNode(_OverflowLLM())
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test"))

    assert result.confidence == 1.0


def test_select_personas_with_llm_uses_llm_response() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["builder_self", "skeptic_self"], "reason": "needs action and critique"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA, HISTORIAN_PERSONA),
        llm=llm,
        min_participants=2,
        max_participants=3,
    )
    selected = discussion._select_personas_with_llm(_make_candidate())
    assert len(selected) == 2
    assert selected[0].id == "builder_self"
    assert selected[1].id == "skeptic_self"


def test_moderator_judgment_detects_convergence() -> None:
    llm = _FakeLLM({"moderator": '{"converged": true, "emergent_persona": "none", "reason": "stable consensus"}'})
    discussion = ProactivePersonaDiscussion(llm=llm)
    judgment = discussion._moderator_judgment(
        {"analyst_self": 0.8, "builder_self": 0.75},
        ["turn-1: discussion"],
        2,
    )
    assert judgment["converged"] is True
    assert judgment["emergent_persona"] == "none"


def test_moderator_judgment_spawns_emergent_persona() -> None:
    llm = _FakeLLM({"moderator": '{"converged": false, "emergent_persona": "bridge_self", "reason": "needs bridge"}'})
    discussion = ProactivePersonaDiscussion(llm=llm)
    judgment = discussion._moderator_judgment(
        {"analyst_self": 0.6, "skeptic_self": 0.4},
        ["turn-1: debate"],
        1,
    )
    assert judgment["converged"] is False
    assert judgment["emergent_persona"] == "bridge_self"


def test_discuss_with_llm_blocks_low_scores() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["analyst_self", "skeptic_self"], "reason": "test"}',
        "score": '{"note": "weak idea", "score": 0.2}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
        llm=llm,
        min_participants=2,
        max_participants=2,
    )
    candidate = _make_candidate()
    result = discussion.discuss(candidate)
    # score=0.2 < blocking_threshold=0.35, strong_support=0 < 2 → blocked
    assert result.approved is False
    assert result.blocking_vetos


def test_discuss_with_llm_approves_high_scores() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["analyst_self", "builder_self"], "reason": "test"}',
        "score": '{"note": "strong idea", "score": 0.8}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, BUILDER_PERSONA),
        llm=llm,
        min_participants=2,
        max_participants=2,
    )
    candidate = _make_candidate()
    result = discussion.discuss(candidate)
    assert result.approved is True
    assert result.scores["analyst_self"] == 0.8
    assert result.scores["builder_self"] == 0.8


def test_proactive_persona_discussion_uses_llm_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    personas = (
        PersonaDefinition(id="skeptic_self", description="Challenges assumptions."),
        PersonaDefinition(id="builder_self", description="Proposes steps."),
        PersonaDefinition(id="analyst_self", description="Decomposes questions."),
    )
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["skeptic_self", "builder_self", "analyst_self"], "reason": "test"}',
        "score": '{"note": "good idea", "score": 0.7}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(personas=personas, llm=llm, min_participants=3, max_participants=3)
    monkeypatch.setattr(discussion, "_participants_for_turn", lambda selected, emergent: personas)  # type: ignore[arg-type]
    candidate = IdeaCandidate(
        id="c1",
        title="Test idea",
        body="A test idea for discussion.",
        candidate_type="question",
        confidence=0.8,
        novelty=0.8,
        urgency=0.5,
        interruption_cost=0.2,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )
    result = discussion.discuss(candidate)

    assert result.approved is True
    trace = result.discussion_trace
    assert any("skeptic_self" in entry for entry in trace)
    assert any("builder_self" in entry for entry in trace)
    assert any("analyst_self" in entry for entry in trace)


# --- Legacy persona node tests (unaffected by proactive scoring changes) ---


def test_llm_backed_persona_node_generates_distinct_notes() -> None:
    from nuself.agent.persona import LLMBackedPersonaNode, PersonaDefinition, PersonaInput

    class _LegacyFakeLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            text = json.dumps([{"role": m.role, "content": m.content} for m in messages])
            if "skeptic_self" in text:
                return "Skeptic challenges the core assumption here."
            if "builder_self" in text:
                return "Builder proposes three concrete steps to act on this."
            return "Analyst breaks this into components and implications."

    llm = _LegacyFakeLLM()
    node = LLMBackedPersonaNode(llm)

    analyst = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    skeptic = PersonaDefinition(id="skeptic_self", description="Challenges assumptions.")
    builder = PersonaDefinition(id="builder_self", description="Proposes steps.")

    inp = PersonaInput(user_message="Test candidate")

    a = node(analyst, inp)
    s = node(skeptic, inp)
    b = node(builder, inp)

    assert a.notes[0] == "Analyst breaks this into components and implications."
    assert s.notes[0] == "Skeptic challenges the core assumption here."
    assert b.notes[0] == "Builder proposes three concrete steps to act on this."
    assert a.notes[0] != s.notes[0]
    assert s.notes[0] != b.notes[0]


def test_llm_backed_synthesizer_node_produces_summary() -> None:
    from nuself.agent.persona import (
        LLMBackedSynthesizerNode,
        PersonaContribution,
        PersonaTurnState,
        PersonaInput,
    )

    class _EchoLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return "Summary of the discussion."

    llm = _EchoLLM()
    node = LLMBackedSynthesizerNode(llm)

    state = PersonaTurnState(
        input=PersonaInput(user_message="test"),
        selected_personas=(),
        contributions=(
            PersonaContribution(persona_id="a", notes=("note a",)),
            PersonaContribution(persona_id="b", notes=("note b",)),
        ),
    )
    result = node(state)
    assert result is not None
    assert result.summary == "Summary of the discussion."
    assert result.source_personas == ("a", "b")


def _spawn_bridge_judgment(
    scores: dict[str, float],
    trace: list[str],
    turn: int,
) -> dict[str, object]:
    del scores, trace, turn
    return {"converged": False, "emergent_persona": "bridge_self", "reason": "test"}
