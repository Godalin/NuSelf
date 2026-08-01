"""Competitive persona discussion for high-value proactive candidates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.errors import AgentError
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.config import ConfigSystem, ReflectionSettings
from nuself.llm import LangChainLLMEndpoint
from nuself.domain.proactive import IdeaCandidate
from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    MODERATOR_PERSONA,
    NonBlankText,
    PersonaContribution,
    PersonaDefinition,
    PersonaInput,
    PersonaSynthesisOutput,
    PersonaTurnState,
)
from nuself.persona.graph import (
    AgentBackedSynthesizerNode,
    PersonaGraphDriver,
)
from nuself.persona.audit import report_persona_failure

DiscussionTraceSink = Callable[[str], None]


class PersonaScoreOutput(BaseModel):
    """Structured note and score from a scoring persona node."""

    model_config = ConfigDict(strict=True, extra="forbid")

    note: NonBlankText = Field(
        description="Persona perspective text (1-2 sentences)."
    )
    score: float = Field(
        ge=0,
        le=1,
        description="Support score from 0.0 to 1.0.",
    )


class PersonaSelectionOutput(BaseModel):
    """Structured persona selection from the discussion host."""

    model_config = ConfigDict(strict=True, extra="forbid")

    selected_persona_ids: list[NonBlankText] = Field(
        min_length=1,
        max_length=5,
        description="Selected persona IDs.",
    )
    reason: NonBlankText = Field(description="Reason for selection.")


class ModeratorJudgmentOutput(BaseModel):
    """Structured moderator judgment from the discussion host."""

    model_config = ConfigDict(strict=True, extra="forbid")

    converged: bool = Field(description="Whether the discussion has converged.")
    emergent_persona: Literal[
        "bridge_self",
        "urgency_self",
        "none",
    ] = Field(description="Emergent persona ID or 'none'.")
    reason: NonBlankText = Field(description="Reason for judgment.")


@dataclass(frozen=True)
class PersonaDiscussionAgents:
    """Typed agent capabilities used by competitive discussion."""

    scoring: StructuredAgent[PersonaScoreOutput]
    selection: StructuredAgent[PersonaSelectionOutput]
    moderator: StructuredAgent[ModeratorJudgmentOutput]


def default_persona_discussion_agents(
    project_root: Path | None = None,
    *,
    endpoints: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> PersonaDiscussionAgents:
    """Build all typed discussion decision agents."""
    return PersonaDiscussionAgents(
        scoring=default_structured_agent(
            PersonaScoreOutput,
            project_root=project_root,
            component="persona",
            endpoints=endpoints,
        ),
        selection=default_structured_agent(
            PersonaSelectionOutput,
            project_root=project_root,
            component="persona",
            endpoints=endpoints,
        ),
        moderator=default_structured_agent(
            ModeratorJudgmentOutput,
            project_root=project_root,
            component="persona",
            endpoints=endpoints,
        ),
    )


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


class AgentBackedScoringPersonaNode:
    """Typed-agent persona node that generates a note and 0-1 score."""

    def __init__(
        self,
        agent: StructuredAgent[PersonaScoreOutput],
        *,
        language_preference: str = "en",
        project_root: Path | None = None,
    ) -> None:
        self._agent = agent
        self._language_preference = language_preference
        self._project_root = project_root

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
            f"{response_language}"
        )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content="Respond with your perspective and score."),
        ]
        try:
            output = self._agent.invoke(messages)
        except AgentError as exc:
            report_persona_failure(
                exc,
                event="persona_discussion_degraded",
                project_root=self._project_root,
                metadata={"stage": "scoring"},
            )
            note = f"{persona.id} considered the topic."
            score = 0.5
        else:
            note = output.note
            score = output.score

        return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=score)


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
        agents: PersonaDiscussionAgents | None = None,
        synthesis_agent: StructuredAgent[PersonaSynthesisOutput] | None = None,
        language_preference: str = "en",
        project_root: Path | None = None,
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
        self._agents = agents
        self._language_preference = language_preference
        self._project_root = project_root

        if agents is not None:
            synthesizer_node = (
                AgentBackedSynthesizerNode(
                    synthesis_agent,
                    language_preference=language_preference,
                    project_root=project_root,
                )
                if synthesis_agent is not None
                else None
            )
            self._driver = PersonaGraphDriver(
                persona_node=AgentBackedScoringPersonaNode(
                    agents.scoring,
                    language_preference=language_preference,
                    project_root=project_root,
                ),
                synthesizer_node=synthesizer_node,
            )
        else:
            self._driver = PersonaGraphDriver()

    def discuss(
        self,
        candidate: IdeaCandidate,
        *,
        on_trace_entry: DiscussionTraceSink | None = None,
    ) -> PersonaCompetitionResult:
        selected = self._select_personas(candidate)
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
            emergent_pid = judgment.emergent_persona
            if emergent_pid != "none":
                new_emergent = self._create_emergent_persona(emergent_pid)
                if new_emergent is not None:
                    emergent = new_emergent
            if judgment.converged:
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

    def _select_personas(
        self,
        candidate: IdeaCandidate,
    ) -> tuple[PersonaDefinition, ...]:
        pool = [p for p in self._personas if p.id != "synthesizer_self"]
        if not pool:
            return ()
        if self._agents is None:
            count = min(self._max_participants, len(pool))
            return tuple(pool[:count])

        persona_lines = [f"- {p.id}: {p.description}" for p in pool]
        system = (
            "You are the Discussion Host. Select the 3-5 most relevant personas to discuss this reflection idea.\n\n"
            "Explain why the selected personas fit the candidate."
        )
        user = (
            "Available personas:\n"
            + "\n".join(persona_lines)
            + f"\n\nCandidate: {candidate.title}\n{candidate.body}\n"
            f"Type: {candidate.candidate_type} | Confidence: {candidate.confidence:.2f} | "
            f"Novelty: {candidate.novelty:.2f} | Urgency: {candidate.urgency:.2f}"
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        try:
            output = self._agents.selection.invoke(messages)
            selected_ids = output.selected_persona_ids
        except AgentError as exc:
            report_persona_failure(
                exc,
                event="persona_discussion_degraded",
                project_root=self._project_root,
                metadata={"stage": "selection"},
            )
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
            if self._agents is not None:
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
        # Only the persona note is needed here; skip synthesis to avoid an unused
        # synthesizer LLM call on every moderator turn (up to max_turns per debate).
        result = self._driver.run_personas_only(turn_state)
        if result.contributions and result.contributions[0].notes:
            return result.contributions[0].notes[0]
        return "Moderator asks the discussion to converge."

    def _moderator_judgment(
        self,
        scores: dict[str, float],
        discussion_trace: list[str],
        turn_number: int,
    ) -> ModeratorJudgmentOutput:
        if self._agents is None:
            return ModeratorJudgmentOutput(
                converged=False,
                emergent_persona="none",
                reason="no agent",
            )

        score_lines = [f"- {pid}: {score:.2f}" for pid, score in scores.items()]
        system = (
            "You are the moderator for a competitive persona debate.\n"
            "After reviewing the current scores and discussion, judge whether the discussion has converged "
            "and whether an emergent persona should join the next round."
        )
        user = (
            "Current scores:\n"
            + "\n".join(score_lines)
            + "\n\nDiscussion trace:\n"
            + "\n".join(discussion_trace[-10:])
            + f"\n\nTurn {turn_number} of {self._max_turns}."
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        try:
            return self._agents.moderator.invoke(messages)
        except AgentError as exc:
            report_persona_failure(
                exc,
                event="persona_discussion_degraded",
                project_root=self._project_root,
                metadata={"stage": "moderator"},
            )
            return ModeratorJudgmentOutput(
                converged=False,
                emergent_persona="none",
                reason="fallback",
            )

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


class SharedPersonaDiscussionService:
    """Shared entry point for competitive persona discussion."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        config: ReflectionSettings | None = None,
        discussion: ProactivePersonaDiscussion | None = None,
        agents: PersonaDiscussionAgents | None = None,
        synthesis_agent: StructuredAgent[PersonaSynthesisOutput] | None = None,
        language_preference: str | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        if discussion is not None:
            self._discussion = discussion
            return
        if config is None or language_preference is None:
            system_config = ConfigSystem.load(project_root=project_root)
            if config is None:
                config = system_config.reflection
            if language_preference is None:
                language_preference = system_config.chat.language_preference
        if agents is None:
            agents = default_persona_discussion_agents(
                project_root,
                endpoints=langchain_models,
            )
        if synthesis_agent is None:
            synthesis_agent = default_structured_agent(
                PersonaSynthesisOutput,
                project_root=project_root,
                component="persona",
                endpoints=langchain_models,
            )
        self._discussion = ProactivePersonaDiscussion(
            config=config,
            agents=agents,
            synthesis_agent=synthesis_agent,
            language_preference=language_preference,
            project_root=project_root,
        )

    def discuss(
        self,
        candidate: IdeaCandidate,
        *,
        on_trace_entry: DiscussionTraceSink | None = None,
    ) -> PersonaCompetitionResult:
        return self._discussion.discuss(candidate, on_trace_entry=on_trace_entry)
