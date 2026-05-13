# pyright: reportPrivateUsage=false
"""Tests for competitive proactive persona discussion."""

from __future__ import annotations

import pytest

from nuself.agent.persona import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    HISTORIAN_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaSynthesis,
    PersonaTurnState,
)
from nuself.domain.proactive import IdeaCandidate
from nuself.proactive_persona import (
    PersonaCompetitionResult,
    ProactivePersonaDiscussion,
)


class _FakePersonaDriver:
    def run(self, turn_state: PersonaTurnState) -> PersonaTurnState:
        persona = turn_state.selected_personas[0]
        note = f"{persona.id}|{turn_state.input.memory_context}"
        return PersonaTurnState(
            input=turn_state.input,
            selected_personas=turn_state.selected_personas,
            contributions=(PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0),),
            synthesis=PersonaSynthesis(summary=note, source_personas=(persona.id,), confidence=0.0),
        )


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


def test_discuss_approves_strong_candidate() -> None:
    discussion = ProactivePersonaDiscussion(min_participants=2, max_participants=4)
    candidate = _make_candidate(confidence=0.9, novelty=0.9, interruption_cost=0.1)
    result = discussion.discuss(candidate)
    assert isinstance(result, PersonaCompetitionResult)
    assert result.approved is True
    assert result.scores
    assert result.reason.startswith("approved after ")


def test_discuss_blocks_high_interruption() -> None:
    from nuself.agent.persona import SKEPTIC_PERSONA, ANALYST_PERSONA

    discussion = ProactivePersonaDiscussion(
        personas=(SKEPTIC_PERSONA, ANALYST_PERSONA),
        min_participants=2,
        max_participants=2,
    )
    candidate = _make_candidate(confidence=0.9, novelty=0.9, interruption_cost=0.9, urgency=0.2)
    result = discussion.discuss(candidate)
    # Skeptic should downscore high interruption; verify its score is lower than analyst
    if "skeptic_self" in result.scores and "analyst_self" in result.scores:
        assert result.scores["skeptic_self"] < result.scores["analyst_self"]
    elif "skeptic_self" in result.scores:
        # Skeptic alone with high interruption should score below override threshold
        assert result.scores["skeptic_self"] < 0.8


def test_select_personas_random_subset() -> None:
    personas = (ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA, HISTORIAN_PERSONA)
    discussion = ProactivePersonaDiscussion(personas=personas, min_participants=2, max_participants=3)
    selected = discussion._select_personas()
    assert 2 <= len(selected) <= 3
    assert all(p.id != "synthesizer_self" for p in selected)


def test_heuristic_score_builder_favors_action() -> None:
    discussion = ProactivePersonaDiscussion(min_participants=1, max_participants=1)
    action = _make_candidate(candidate_type="action", confidence=0.7, novelty=0.7)
    question = _make_candidate(candidate_type="question", confidence=0.7, novelty=0.7)
    from nuself.agent.persona import PersonaContribution

    action_score = discussion._heuristic_score(
        action, PersonaContribution(persona_id="builder_self")
    )
    question_score = discussion._heuristic_score(
        question, PersonaContribution(persona_id="builder_self")
    )
    assert action_score > question_score


def test_heuristic_score_skeptic_downscores_interruption() -> None:
    discussion = ProactivePersonaDiscussion(min_participants=1, max_participants=1)
    low_int = _make_candidate(interruption_cost=0.1, confidence=0.8, novelty=0.8)
    high_int = _make_candidate(interruption_cost=0.9, confidence=0.8, novelty=0.8)
    from nuself.agent.persona import PersonaContribution

    low_score = discussion._heuristic_score(
        low_int, PersonaContribution(persona_id="skeptic_self")
    )
    high_score = discussion._heuristic_score(
        high_int, PersonaContribution(persona_id="skeptic_self")
    )
    assert high_score < low_score


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
    assert result.approved is False
    assert result.blocking_vetos


def test_discuss_shares_context_across_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
        min_participants=2,
        max_participants=2,
        max_turns=3,
        consensus_spread_threshold=0.0,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr("nuself.proactive_persona.random.sample", _sample_first)
    monkeypatch.setattr("nuself.proactive_persona.random.randint", _pick_upper_bound)
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
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr("nuself.proactive_persona.random.sample", _sample_first)
    monkeypatch.setattr("nuself.proactive_persona.random.randint", _pick_upper_bound)
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


def _sample_first(seq: list[object], k: int) -> list[object]:
    return list(seq)[:k]


def _pick_upper_bound(low: int, high: int) -> int:
    return high


# --- LLM-backed persona node tests ---

class _FakePersonaLLM:
    """Deterministic LLM that returns persona-specific responses."""

    def complete(self, messages: object) -> str:
        # Extract persona id from system prompt
        import json
        text = json.dumps([{"role": m.role, "content": m.content} for m in messages])  # type: ignore[union-attr]
        if "skeptic_self" in text:
            return "Skeptic challenges the core assumption here."
        if "builder_self" in text:
            return "Builder proposes three concrete steps to act on this."
        if "care_self" in text:
            return "Care notices the emotional weight and suggests pacing."
        return "Analyst breaks this into components and implications."


def test_llm_backed_persona_node_generates_distinct_notes() -> None:
    from nuself.agent.persona import LLMBackedPersonaNode, PersonaDefinition, PersonaInput

    llm = _FakePersonaLLM()
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
        def complete(self, messages: object) -> str:
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


def test_proactive_persona_discussion_uses_llm_when_provided() -> None:
    from nuself.proactive_persona import ProactivePersonaDiscussion
    from nuself.domain.proactive import IdeaCandidate
    from nuself.agent.persona import PersonaDefinition

    personas = (
        PersonaDefinition(id="skeptic_self", description="Challenges assumptions."),
        PersonaDefinition(id="builder_self", description="Proposes steps."),
        PersonaDefinition(id="analyst_self", description="Decomposes questions."),
    )
    discussion = ProactivePersonaDiscussion(personas=personas, llm=_FakePersonaLLM(), min_participants=3, max_participants=3)
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

    # With the fake LLM, all personas return non-empty distinct notes,
    # so the composite should be above threshold and it should approve.
    assert result.approved is True
    trace = result.discussion_trace
    assert any("skeptic_self" in entry for entry in trace)
    assert any("builder_self" in entry for entry in trace)
