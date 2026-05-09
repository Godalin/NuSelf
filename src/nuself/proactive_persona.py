"""Competitive persona discussion for high-value proactive candidates."""

from __future__ import annotations

from dataclasses import dataclass
import random

from nuself.agent.persona import (
    BUILTIN_PERSONAS,
    PersonaContribution,
    PersonaDefinition,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
)
from nuself.domain.proactive import IdeaCandidate


@dataclass(frozen=True)
class PersonaCompetitionResult:
    """Outcome of a competitive persona discussion over one candidate."""

    approved: bool
    winner_persona_ids: tuple[str, ...]
    revised_title: str
    revised_body: str
    scores: dict[str, float]
    blocking_vetos: tuple[str, ...]
    reason: str


class ProactivePersonaDiscussion:
    """Run a randomized competitive persona debate over a candidate."""

    def __init__(
        self,
        *,
        personas: tuple[PersonaDefinition, ...] | None = None,
        min_participants: int = 2,
        max_participants: int = 4,
        blocking_threshold: float = 0.3,
        override_threshold: float = 0.8,
        composite_threshold: float = 0.5,
    ) -> None:
        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._min_participants = min(min_participants, max_participants)
        self._max_participants = max(min_participants, max_participants)
        self._blocking_threshold = blocking_threshold
        self._override_threshold = override_threshold
        self._composite_threshold = composite_threshold
        self._driver = PersonaGraphDriver()

    def discuss(self, candidate: IdeaCandidate) -> PersonaCompetitionResult:
        selected = self._select_personas()
        if not selected:
            return PersonaCompetitionResult(
                approved=True,
                winner_persona_ids=(),
                revised_title=candidate.title,
                revised_body=candidate.body,
                scores={},
                blocking_vetos=(),
                reason="no personas available",
            )

        scores = self._score_candidate(candidate, selected)
        blocking = tuple(
            pid for pid, score in scores.items() if score < self._blocking_threshold
        )
        strong_support = sum(1 for s in scores.values() if s > self._override_threshold)

        if blocking and strong_support < 2:
            return PersonaCompetitionResult(
                approved=False,
                winner_persona_ids=(),
                revised_title=candidate.title,
                revised_body=candidate.body,
                scores=scores,
                blocking_vetos=blocking,
                reason=f"blocked by {', '.join(blocking)}",
            )

        composite = sum(scores.values()) / len(scores) if scores else 0.0
        if composite < self._composite_threshold:
            return PersonaCompetitionResult(
                approved=False,
                winner_persona_ids=(),
                revised_title=candidate.title,
                revised_body=candidate.body,
                scores=scores,
                blocking_vetos=blocking,
                reason=f"composite {composite:.2f} below threshold",
            )

        winners = tuple(
            pid for pid, score in scores.items() if score >= composite
        )
        return PersonaCompetitionResult(
            approved=True,
            winner_persona_ids=winners,
            revised_title=candidate.title,
            revised_body=candidate.body,
            scores=scores,
            blocking_vetos=blocking,
            reason="approved after competitive discussion",
        )

    def _select_personas(self) -> tuple[PersonaDefinition, ...]:
        pool = [p for p in self._personas if p.id != "synthesizer_self"]
        if not pool:
            return ()
        count = random.randint(self._min_participants, min(self._max_participants, len(pool)))
        selected = random.sample(pool, count)
        return tuple(selected)

    def _score_candidate(
        self, candidate: IdeaCandidate, personas: tuple[PersonaDefinition, ...]
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        turn_state = PersonaTurnState(
            input=PersonaInput(
                user_message=f"{candidate.title}\n{candidate.body}",
            ),
            selected_personas=personas,
        )
        result = self._driver.run(turn_state)
        for contrib in result.contributions:
            score = self._heuristic_score(candidate, contrib)
            scores[contrib.persona_id] = score
        return scores

    def _heuristic_score(
        self, candidate: IdeaCandidate, contrib: PersonaContribution
    ) -> float:
        # Base score from candidate confidence and novelty
        base = (candidate.confidence + candidate.novelty) / 2
        # Persona-specific adjustments
        pid = contrib.persona_id
        if pid == "skeptic_self":
            # Skeptic downscores speculative or high-interruption candidates
            if candidate.interruption_cost > 0.6:
                return max(0.0, base - 0.3)
            if candidate.candidate_type in {"contradiction", "question"}:
                return min(1.0, base + 0.1)
        if pid == "builder_self":
            if candidate.candidate_type == "action":
                return min(1.0, base + 0.2)
        if pid == "historian_self":
            if candidate.candidate_type in {"connection", "profile_update"}:
                return min(1.0, base + 0.15)
        if pid == "care_self":
            if candidate.urgency > 0.7:
                return min(1.0, base + 0.1)
            if candidate.interruption_cost > 0.7:
                return max(0.0, base - 0.2)
        if pid == "analyst_self":
            if candidate.evidence_refs:
                return min(1.0, base + 0.1)
        return base
