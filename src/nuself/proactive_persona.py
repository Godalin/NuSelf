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
    MODERATOR_PERSONA,
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
    discussion_trace: tuple[str, ...] = ()
    emergent_persona_ids: tuple[str, ...] = ()


class ProactivePersonaDiscussion:
    """Run a randomized competitive persona debate over a candidate."""

    def __init__(
        self,
        *,
        personas: tuple[PersonaDefinition, ...] | None = None,
        min_participants: int = 2,
        max_participants: int = 4,
        max_turns: int | None = None,
        blocking_threshold: float = 0.3,
        override_threshold: float = 0.8,
        composite_threshold: float = 0.5,
        consensus_spread_threshold: float = 0.2,
        config: object | None = None,
    ) -> None:
        # If config is provided, extract parameters from it
        if config is not None:
            from nuself.config_reflection import ReflectionConfig
            if isinstance(config, ReflectionConfig):
                max_turns = config.max_discussion_rounds
        
        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._min_participants = min(min_participants, max_participants)
        self._max_participants = max(min_participants, max_participants)
        self._max_turns = max(1, max_turns or 9)
        self._blocking_threshold = blocking_threshold
        self._override_threshold = override_threshold
        self._composite_threshold = composite_threshold
        self._consensus_spread_threshold = consensus_spread_threshold
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

        emergent = self._maybe_spawn_emergent_persona(candidate, selected)
        discussion_trace: list[str] = [
            f"candidate: {candidate.title}",
            f"type={candidate.candidate_type} confidence={candidate.confidence:.2f} novelty={candidate.novelty:.2f}",
            candidate.body,
        ]
        round_scores: dict[str, float] = {}
        turn_number = 0
        while turn_number < self._max_turns:
            turn_number += 1
            moderator_note = self._moderator_prompt(candidate, discussion_trace, turn_number)
            discussion_trace.append(f"host: {moderator_note}")
            participants = self._participants_for_turn(selected, emergent)
            round_scores = self._score_candidate(
                candidate,
                participants,
                discussion_trace,
                turn_label=f"turn-{turn_number}",
                turn_number=turn_number,
            )
            if self._round_has_consensus(round_scores):
                discussion_trace.append(f"turn-{turn_number}: reached convergence")
                break
            if turn_number < self._max_turns:
                discussion_trace.append(f"turn-{turn_number}: moderator invites another pass")
        scores = round_scores
        emergent_persona_ids = (emergent.id,) if emergent is not None else ()
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
                discussion_trace=tuple(discussion_trace),
                emergent_persona_ids=emergent_persona_ids,
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
                discussion_trace=tuple(discussion_trace),
                emergent_persona_ids=emergent_persona_ids,
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
            reason=f"approved after {turn_number} discussion turn(s)",
            discussion_trace=tuple(discussion_trace),
            emergent_persona_ids=emergent_persona_ids,
        )

    def _participants_for_turn(
        self,
        selected: tuple[PersonaDefinition, ...],
        emergent: PersonaDefinition | None,
    ) -> tuple[PersonaDefinition, ...]:
        pool = list(selected)
        if emergent is not None:
            pool.append(emergent)
        if not pool:
            return ()
        count = random.randint(1, len(pool))
        chosen = random.sample(pool, count)
        return tuple(chosen)

    def _select_personas(self) -> tuple[PersonaDefinition, ...]:
        pool = [p for p in self._personas if p.id != "synthesizer_self"]
        if not pool:
            return ()
        count = random.randint(self._min_participants, min(self._max_participants, len(pool)))
        selected = random.sample(pool, count)
        return tuple(selected)

    def _score_candidate(
        self,
        candidate: IdeaCandidate,
        personas: tuple[PersonaDefinition, ...],
        discussion_trace: list[str],
        *,
        turn_label: str,
        turn_number: int,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        discussion_context = "\n".join(discussion_trace)
        for persona in personas:
            turn_state = PersonaTurnState(
                input=PersonaInput(
                    user_message=f"{candidate.title}\n{candidate.body}",
                    memory_context=discussion_context,
                ),
                selected_personas=(persona,),
            )
            result = self._driver.run(turn_state)
            if not result.contributions:
                continue
            contrib = result.contributions[0]
            score = self._heuristic_score(candidate, contrib, discussion_context=discussion_context, turn_number=turn_number)
            scores[contrib.persona_id] = score
            note = contrib.notes[0] if contrib.notes else contrib.persona_id
            discussion_trace.append(f"{turn_label}:{contrib.persona_id}: {note}")
            if result.synthesis is not None and result.synthesis.summary:
                discussion_trace.append(f"{turn_label}:synthesis: {result.synthesis.summary}")
            discussion_context = "\n".join(discussion_trace)
        return scores

    def _moderator_prompt(
        self,
        candidate: IdeaCandidate,
        discussion_trace: list[str],
        turn_number: int,
    ) -> str:
        turn_state = PersonaTurnState(
            input=PersonaInput(
                user_message=f"Moderator turn {turn_number}: {candidate.title}",
                memory_context="\n".join(discussion_trace),
            ),
            selected_personas=(MODERATOR_PERSONA,),
        )
        result = self._driver.run(turn_state)
        if result.contributions and result.contributions[0].notes:
            return result.contributions[0].notes[0]
        return "Moderator asks the discussion to converge."

    def _round_has_consensus(self, scores: dict[str, float]) -> bool:
        if not scores:
            return False
        composite = sum(scores.values()) / len(scores)
        spread = max(scores.values()) - min(scores.values())
        support = sum(1 for score in scores.values() if score >= self._override_threshold)
        no_blocking = all(score >= self._blocking_threshold for score in scores.values())
        return (
            composite >= self._composite_threshold
            and spread <= self._consensus_spread_threshold
            and no_blocking
            and support >= 2
        )

    def _maybe_spawn_emergent_persona(
        self,
        candidate: IdeaCandidate,
        selected: tuple[PersonaDefinition, ...],
    ) -> PersonaDefinition | None:
        if not selected:
            return None
        if candidate.candidate_type in {"connection", "contradiction"} and candidate.novelty >= 0.7:
            return PersonaDefinition(
                id="bridge_self",
                description="A temporary bridge persona that links competing ideas and finds a shared frame.",
            )
        if candidate.candidate_type == "question" and candidate.urgency >= 0.8:
            return PersonaDefinition(
                id="urgency_self",
                description="A temporary urgency persona that checks whether the candidate needs immediate attention.",
            )
        return None

    def _heuristic_score(
        self,
        candidate: IdeaCandidate,
        contrib: PersonaContribution,
        *,
        discussion_context: str = "",
        turn_number: int = 1,
    ) -> float:
        # Base score from candidate confidence and novelty
        base = (candidate.confidence + candidate.novelty) / 2
        if turn_number > 1 and discussion_context:
            base = min(1.0, base + min(0.08, 0.02 * (turn_number - 1)))
        if "after hearing" in discussion_context:
            base = min(1.0, base + 0.03)
        if contrib.persona_id == "moderator_self":
            return 0.0
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
