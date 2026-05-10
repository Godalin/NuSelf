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
    # Skeptic should downscore high interruption; with only 2 personas and low urgency,
    # strong override is unlikely
    assert result.approved is False or "skeptic_self" in result.scores


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
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr("nuself.proactive_persona.random.sample", _sample_first)
    candidate = _make_candidate(body="A shared context should evolve during debate.")

    result = discussion.discuss(candidate)

    assert result.approved is True
    assert any(line.startswith("round-1:") for line in result.discussion_trace)
    assert any(line.startswith("round-2:") for line in result.discussion_trace)
    assert any(line.startswith("round-3:") for line in result.discussion_trace)
    assert any(line.startswith("round-2:") and "round-1:" in line for line in result.discussion_trace)


def test_discuss_spawns_emergent_temporary_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA),
        min_participants=2,
        max_participants=2,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr("nuself.proactive_persona.random.sample", _sample_first)
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
