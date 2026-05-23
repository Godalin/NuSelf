"""Competitive persona discussion for high-value proactive candidates."""

from __future__ import annotations

import json

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, Field, ValidationError

from nuself.agent.persona import (
    BUILTIN_PERSONAS,
    LLMBackedSynthesizerNode,
    PersonaContribution,
    PersonaDefinition,
    PersonaGraphDriver,
    PersonaInput,
    MODERATOR_PERSONA,
    PersonaTurnState,
)
from nuself.config import ReflectionSettings
from nuself.domain.proactive import IdeaCandidate
from nuself.llm import ChatLLM, ChatMessage
from nuself.llm import parse_llm_json_object

DiscussionTraceSink = Callable[[str], None]


class PersonaScoreOutput(BaseModel):
    """Structured note and score from a scoring persona node."""

    note: str = Field(description="Persona perspective text (1-2 sentences).")
    score: float = Field(description="Support score from 0.0 to 1.0.")


class PersonaSelectionOutput(BaseModel):
    """Structured persona selection from the discussion host."""

    selected_persona_ids: list[str] = Field(description="Selected persona IDs.")
    reason: str = Field(default="", description="Reason for selection.")


class ModeratorJudgmentOutput(BaseModel):
    """Structured moderator judgment from the discussion host."""

    converged: bool = Field(description="Whether the discussion has converged.")
    emergent_persona: str = Field(default="none", description="Emergent persona ID or 'none'.")
    reason: str = Field(default="", description="Reason for judgment.")


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


class LLMBackedScoringPersonaNode:
    """LLM-driven persona node that generates both a note and a 0-1 score."""

    def __init__(self, llm: ChatLLM, *, language_preference: str = "en") -> None:
        self._llm = llm
        self._language_preference = language_preference

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
        prior = persona_input.memory_context.strip()
        if prior:
            prior_block = f"\nPrior discussion:\n{prior}"
        else:
            prior_block = ""

        response_language = ""
        if self._language_preference != "en":
            response_language = f" Write the note in {self._language_preference}."

        system = (
            f"You are {persona.id} in a competitive discussion about a proactive reflection idea.\n"
            f"Your role: {persona.description}\n\n"
            f"Candidate:\n{persona_input.user_message}{prior_block}\n\n"
            "Give your perspective (1-2 sentences) AND a score (0.0-1.0) for how strongly you support this idea."
            f"{response_language}\n\n"
            'Return ONLY JSON: {"note": "your perspective", "score": 0.7}\n'
            "No markdown fences."
        )

        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content="Respond with your perspective and score."),
        ]
        try:
            raw = self._llm.complete(messages).strip()
            note, score = self._parse_response(raw)
        except (RuntimeError, ValueError, KeyError):
            note = f"{persona.id} considered the topic."
            score = 0.5

        return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=score)

    def _parse_response(self, raw: str) -> tuple[str, float]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        try:
            output = PersonaScoreOutput.model_validate_json(stripped)
            return output.note, max(0.0, min(1.0, output.score))
        except (ValidationError, json.JSONDecodeError):
            pass

        data = parse_llm_json_object(raw)

        note = data.get("note")
        if not isinstance(note, str):
            raise KeyError("missing or invalid note")

        score = data.get("score")
        if isinstance(score, (int, float)):
            score = max(0.0, min(1.0, float(score)))
        else:
            raise KeyError("missing or invalid score")

        return note, score


class ProactivePersonaDiscussion:
    """Run a competitive persona debate over a candidate."""

    def __init__(
        self,
        *,
        personas: tuple[PersonaDefinition, ...] | None = None,
        min_participants: int = 3,
        max_participants: int = 5,
        max_turns: int | None = None,
        blocking_threshold: float = 0.35,
        override_threshold: float = 0.7,
        composite_threshold: float = 0.4,
        consensus_spread_threshold: float = 0.15,
        config: ReflectionSettings | None = None,
        llm: ChatLLM | None = None,
        language_preference: str = "en",
    ) -> None:
        if config is not None:
            max_turns = config.moderator.max_discussion_rounds
            min_participants = config.discussion.min_participants
            max_participants = config.discussion.max_participants
            blocking_threshold = config.discussion.blocking_threshold
            override_threshold = config.discussion.override_threshold
            composite_threshold = config.discussion.composite_threshold
            consensus_spread_threshold = config.discussion.consensus_spread_threshold

        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._min_participants = min(min_participants, max_participants)
        self._max_participants = max(min_participants, max_participants)
        self._max_turns = max(1, max_turns or 12)
        self._blocking_threshold = blocking_threshold
        self._override_threshold = override_threshold
        self._composite_threshold = composite_threshold
        self._consensus_spread_threshold = consensus_spread_threshold
        self._llm = llm
        self._language_preference = language_preference

        if llm is not None:
            self._driver = PersonaGraphDriver(
                persona_node=LLMBackedScoringPersonaNode(llm, language_preference=language_preference),
                synthesizer_node=LLMBackedSynthesizerNode(llm, language_preference=language_preference),
            )
        else:
            self._driver = PersonaGraphDriver()

    def discuss(
        self,
        candidate: IdeaCandidate,
        *,
        on_trace_entry: DiscussionTraceSink | None = None,
    ) -> PersonaCompetitionResult:
        selected = self._select_personas_with_llm(candidate)
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

        discussion_trace: list[str] = []
        self._append_trace(discussion_trace, f"candidate: {candidate.title}", on_trace_entry)
        self._append_trace(
            discussion_trace,
            f"type={candidate.candidate_type} confidence={candidate.confidence:.2f} novelty={candidate.novelty:.2f}",
            on_trace_entry,
        )
        self._append_trace(discussion_trace, candidate.body, on_trace_entry)
        round_scores: dict[str, float] = {}
        emergent: PersonaDefinition | None = None
        turn_number = 0
        while turn_number < self._max_turns:
            turn_number += 1
            moderator_note = self._moderator_prompt(candidate, discussion_trace, turn_number)
            self._append_trace(discussion_trace, f"host: {moderator_note}", on_trace_entry)
            participants = self._participants_for_turn(selected, emergent)
            round_scores = self._score_candidate(
                candidate,
                participants,
                discussion_trace,
                turn_label=f"turn-{turn_number}",
                turn_number=turn_number,
                on_trace_entry=on_trace_entry,
            )
            judgment = self._moderator_judgment(round_scores, discussion_trace, turn_number)
            emergent_pid = judgment.get("emergent_persona")
            if isinstance(emergent_pid, str) and emergent_pid not in ("none", ""):
                new_emergent = self._create_emergent_persona(emergent_pid)
                if new_emergent is not None:
                    emergent = new_emergent
            if judgment.get("converged"):
                self._append_trace(discussion_trace, f"turn-{turn_number}: reached convergence", on_trace_entry)
                break
            if turn_number < self._max_turns:
                self._append_trace(
                    discussion_trace,
                    f"turn-{turn_number}: moderator invites another pass",
                    on_trace_entry,
                )
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
        if emergent is not None:
            pool = list(selected[: max(0, self._max_participants - 1)])
            pool.append(emergent)
        else:
            pool = list(selected)
        if not pool:
            return ()
        return tuple(pool[: self._max_participants])

    def _select_personas_with_llm(self, candidate: IdeaCandidate) -> tuple[PersonaDefinition, ...]:
        pool = [p for p in self._personas if p.id != "synthesizer_self"]
        if not pool:
            return ()
        if self._llm is None:
            count = min(self._max_participants, len(pool))
            return tuple(pool[:count])

        persona_lines = [f"- {p.id}: {p.description}" for p in pool]
        system = (
            "You are the Discussion Host. Select the 3-5 most relevant personas to discuss this reflection idea.\n\n"
            'Return ONLY JSON: {"selected_persona_ids": [...], "reason": "..."}\n'
            "No markdown fences."
        )
        user = (
            "Available personas:\n"
            + "\n".join(persona_lines)
            + f"\n\nCandidate: {candidate.title}\n{candidate.body}\n"
            f"Type: {candidate.candidate_type} | Confidence: {candidate.confidence:.2f} | "
            f"Novelty: {candidate.novelty:.2f} | Urgency: {candidate.urgency:.2f}"
        )
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]
        try:
            raw = self._llm.complete(messages).strip()
            selected_ids = self._parse_selected_personas(raw)
        except (RuntimeError, ValueError, KeyError):
            selected_ids = []

        selected: list[PersonaDefinition] = []
        persona_by_id = {p.id: p for p in pool}
        for pid in selected_ids:
            if pid in persona_by_id:
                selected.append(persona_by_id[pid])

        if not selected:
            count = min(self._max_participants, len(pool))
            return tuple(pool[:count])

        return tuple(selected)

    def _parse_selected_personas(self, raw: str) -> list[str]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        try:
            output = PersonaSelectionOutput.model_validate_json(stripped)
            return output.selected_persona_ids
        except (ValidationError, json.JSONDecodeError):
            pass

        data = parse_llm_json_object(raw)

        selected_ids = data.get("selected_persona_ids")
        if not isinstance(selected_ids, list):
            raise KeyError("missing or invalid selected_persona_ids")
        selected_ids_list = cast(list[object], selected_ids)
        return [pid for pid in selected_ids_list if isinstance(pid, str)]

    def _score_candidate(
        self,
        candidate: IdeaCandidate,
        personas: tuple[PersonaDefinition, ...],
        discussion_trace: list[str],
        *,
        turn_label: str,
        turn_number: int,
        on_trace_entry: DiscussionTraceSink | None,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        discussion_context = "\n".join(discussion_trace)
        turn_state = PersonaTurnState(
            input=PersonaInput(
                user_message=f"{candidate.title}\n{candidate.body}",
                memory_context=discussion_context,
            ),
            selected_personas=personas,
        )
        result = self._driver.run(turn_state)
        for contrib in result.contributions:
            if self._llm is not None:
                score = contrib.confidence if contrib.confidence is not None else 0.5
            else:
                score = 0.5
            scores[contrib.persona_id] = score
            note = contrib.notes[0] if contrib.notes else contrib.persona_id
            self._append_trace(discussion_trace, f"{turn_label}:{contrib.persona_id}: {note}", on_trace_entry)
        if result.synthesis is not None and result.synthesis.summary:
            self._append_trace(discussion_trace, f"{turn_label}:synthesis: {result.synthesis.summary}", on_trace_entry)
        return scores

    def _append_trace(
        self,
        discussion_trace: list[str],
        entry: str,
        on_trace_entry: DiscussionTraceSink | None,
    ) -> None:
        discussion_trace.append(entry)
        if on_trace_entry is not None:
            on_trace_entry(entry)

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

    def _moderator_judgment(
        self,
        scores: dict[str, float],
        discussion_trace: list[str],
        turn_number: int,
    ) -> dict[str, object]:
        if self._llm is None:
            return {"converged": False, "emergent_persona": "none", "reason": "no llm"}

        score_lines = [f"- {pid}: {score:.2f}" for pid, score in scores.items()]
        system = (
            "You are the moderator for a competitive persona debate.\n"
            "After reviewing the current scores and discussion, judge whether the discussion has converged "
            "and whether an emergent persona should join the next round.\n\n"
            'Return ONLY JSON: {"converged": true|false, "emergent_persona": "bridge_self|urgency_self|none", "reason": "..."}\n'
            "No markdown fences."
        )
        user = (
            "Current scores:\n"
            + "\n".join(score_lines)
            + "\n\nDiscussion trace:\n"
            + "\n".join(discussion_trace[-10:])
            + f"\n\nTurn {turn_number} of {self._max_turns}."
        )
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]
        try:
            raw = self._llm.complete(messages).strip()
            return self._parse_moderator_judgment(raw)
        except (RuntimeError, ValueError, KeyError):
            return {"converged": False, "emergent_persona": "none", "reason": "fallback"}

    def _parse_moderator_judgment(self, raw: str) -> dict[str, object]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        try:
            output = ModeratorJudgmentOutput.model_validate_json(stripped)
            return {
                "converged": output.converged,
                "emergent_persona": output.emergent_persona,
                "reason": output.reason,
            }
        except (ValidationError, json.JSONDecodeError):
            pass

        data = parse_llm_json_object(raw)

        converged = data.get("converged")
        if isinstance(converged, bool):
            pass
        elif isinstance(converged, str):
            converged = converged.lower() in {"true", "yes", "1"}
        else:
            converged = False

        emergent = data.get("emergent_persona")
        if not isinstance(emergent, str):
            emergent = "none"

        reason = data.get("reason")
        if not isinstance(reason, str):
            reason = ""

        return {
            "converged": converged,
            "emergent_persona": emergent,
            "reason": reason,
        }

    def _create_emergent_persona(self, persona_id: str) -> PersonaDefinition | None:
        if persona_id == "bridge_self":
            return PersonaDefinition(
                id="bridge_self",
                description="A temporary bridge persona that links competing ideas and finds a shared frame.",
            )
        if persona_id == "urgency_self":
            return PersonaDefinition(
                id="urgency_self",
                description="A temporary urgency persona that checks whether the candidate needs immediate attention.",
            )
        return None
