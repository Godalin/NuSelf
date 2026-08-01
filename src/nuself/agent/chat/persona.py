"""Persona consultation orchestration for the chat runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nuself.agent.failover import is_recoverable_agent_failure
from nuself.domain.proactive import IdeaCandidate
from nuself.llm import LangChainLLMEndpoint
from nuself.memory.query import MemoryQuery, MemoryService
from nuself.persona import (
    AgentBackedActivationPolicy,
    AgentBackedPersonaNode,
    AgentBackedSynthesizerNode,
    PersonaDefinition,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
    SharedPersonaDiscussionService,
    persona_graph_agents,
)
from nuself.persona.audit import (
    report_persona_failure,
    write_persona_audit,
)
from nuself.runtime.context import current_runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_message


class ConversationPersonaOrchestrator:
    """Runs bounded selves consultation and optional competitive discussion."""

    def __init__(
        self,
        *,
        project_root: Path | None,
        langchain_models: tuple[LangChainLLMEndpoint, ...],
        language_preference: str,
        memory_query_service: MemoryService,
        persona_definitions: tuple[PersonaDefinition, ...],
    ) -> None:
        self._project_root = project_root
        self._memory_query_service = memory_query_service
        self._persona_definitions = persona_definitions
        graph_agents = (
            persona_graph_agents(
                langchain_models,
                project_root=project_root,
            )
            if langchain_models
            else None
        )
        self._activation_policy = AgentBackedActivationPolicy(
            self._persona_definitions,
            agent=(
                graph_agents.activation
                if graph_agents is not None
                else None
            ),
            project_root=project_root,
        )
        self._persona_driver = PersonaGraphDriver(
            persona_node=(
                AgentBackedPersonaNode(
                    graph_agents.contribution,
                    language_preference=language_preference,
                    project_root=project_root,
                )
                if graph_agents is not None
                else None
            ),
            synthesizer_node=(
                AgentBackedSynthesizerNode(
                    graph_agents.synthesis,
                    language_preference=language_preference,
                    project_root=project_root,
                )
                if graph_agents is not None
                else None
            ),
        )
        self._discussion_service = SharedPersonaDiscussionService(
            project_root=project_root,
            synthesis_agent=(
                graph_agents.synthesis
                if graph_agents is not None
                else None
            ),
            language_preference=language_preference,
        )

    def consult(
        self,
        topic: str,
        mode: str = "consult",
        context: str | None = None,
    ) -> str:
        conversation_id = current_runtime_context().conversation_id or "default"
        memory_context = self._memory_query_service.pack(
            MemoryQuery(text=topic)
        ).text
        extra_context = context.strip() if isinstance(context, str) else ""
        combined_context = "\n\n".join(
            part for part in (memory_context, extra_context) if part
        )
        persona_input = PersonaInput(
            user_message=topic,
            memory_context=combined_context,
        )
        activation = self._activation_policy.decide(persona_input)
        selected_personas = (
            activation.selected_personas or self._default_personas()
        )
        turn_state = PersonaTurnState(
            input=persona_input,
            selected_personas=selected_personas,
        )
        updated_turn_state = self._persona_driver.run(turn_state)
        trigger = activation.trigger or "selves_consult"
        self._write_summary_log(
            updated_turn_state,
            conversation_id=conversation_id,
            trigger=trigger,
        )

        force_discussion = mode.strip().casefold() in {
            "discussion",
            "discuss",
            "debate",
            "competitive",
        }
        should_escalate = activation.should_escalate or force_discussion
        escalation_reason = activation.escalation_reason or (
            "requested discussion mode"
            if force_discussion
            else "consultation only"
        )
        self._write_host_decision_log(
            conversation_id=conversation_id,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
        discussion_note = self._run_discussion(
            topic=topic,
            conversation_id=conversation_id,
            trigger=trigger,
            turn_state=updated_turn_state,
            should_escalate=should_escalate,
        )
        return _format_consult_result(
            updated_turn_state,
            trigger=trigger,
            discussion_note=discussion_note,
        )

    def _run_discussion(
        self,
        *,
        topic: str,
        conversation_id: str,
        trigger: str,
        turn_state: PersonaTurnState,
        should_escalate: bool,
    ) -> str:
        if not should_escalate:
            return ""
        step_number = 0

        def record_step(entry: str) -> None:
            nonlocal step_number
            del entry
            step_number += 1
            self._write_discussion_step_log(conversation_id, step_number)

        try:
            candidate = self._build_candidate(
                conversation_id=conversation_id,
                user_message=topic,
                title=(
                    topic.splitlines()[0]
                    if topic.splitlines()
                    else topic
                )[:120],
                source_summary=(
                    turn_state.synthesis.summary
                    if turn_state.synthesis is not None
                    else ""
                ),
            )
            result = self._discussion_service.discuss(
                candidate,
                on_trace_entry=record_step,
            )
            write_persona_audit(
                "persona_discussion",
                project_root=self._project_root,
                conversation_id=conversation_id,
                metadata={
                    "candidate_id": candidate.id,
                    "approved": result.approved,
                    "winner_count": len(result.winner_persona_ids),
                    "emergent_count": len(result.emergent_persona_ids),
                    "blocking_veto_count": len(result.blocking_vetos),
                    "score_count": len(result.scores),
                    "discussion_steps": len(result.discussion_trace),
                },
            )
            return f"\nDiscussion result: {result.reason}"
        except Exception as exc:
            if not is_recoverable_agent_failure(exc):
                raise
            error = diagnostic_exception_message(exc)
            report_persona_failure(
                exc,
                event="persona_discussion_failure",
                project_root=self._project_root,
            )
            return f"\nDiscussion failed: {error}"

    def _default_personas(self) -> tuple[PersonaDefinition, ...]:
        preferred = ("analyst_self", "skeptic_self", "builder_self")
        by_id = {
            persona.id: persona
            for persona in self._persona_definitions
        }
        selected = tuple(
            by_id[persona_id]
            for persona_id in preferred
            if persona_id in by_id
        )
        return selected or tuple(self._persona_definitions[:3])

    def _write_summary_log(
        self,
        turn_state: PersonaTurnState,
        *,
        conversation_id: str,
        trigger: str,
    ) -> None:
        del trigger
        write_persona_audit(
            "persona_summary",
            project_root=self._project_root,
            conversation_id=conversation_id,
            metadata={
                "persona_count": len(turn_state.contributions),
                "has_synthesis": turn_state.synthesis is not None,
            },
        )

    def _write_host_decision_log(
        self,
        *,
        conversation_id: str,
        should_escalate: bool,
        escalation_reason: str,
    ) -> None:
        del escalation_reason
        write_persona_audit(
            "host_discussion_decision",
            project_root=self._project_root,
            conversation_id=conversation_id,
            metadata={"should_escalate": should_escalate},
        )

    def _write_discussion_step_log(
        self,
        conversation_id: str,
        step_number: int,
    ) -> None:
        write_persona_audit(
            "persona_discussion_step",
            project_root=self._project_root,
            conversation_id=conversation_id,
            metadata={"step_number": step_number},
        )

    @staticmethod
    def _build_candidate(
        *,
        conversation_id: str,
        user_message: str,
        title: str,
        source_summary: str,
    ) -> IdeaCandidate:
        now = datetime.now(UTC)
        return IdeaCandidate(
            id=f"chat-{conversation_id}-{int(now.timestamp())}",
            title=title,
            body=user_message,
            candidate_type=(
                "question" if "?" in user_message else "action"
            ),
            confidence=0.8,
            novelty=0.5,
            urgency=0.2,
            interruption_cost=0.1,
            evidence_refs=(),
            source_summary=source_summary,
            created_at=now.isoformat(),
        )


def _format_consult_result(
    turn_state: PersonaTurnState,
    *,
    trigger: str,
    discussion_note: str = "",
) -> str:
    lines = ["Selves consultation result:", f"trigger: {trigger}"]
    if turn_state.contributions:
        lines.append("persona notes:")
        for contribution in turn_state.contributions:
            note = (
                contribution.notes[0]
                if contribution.notes
                else "(no note)"
            )
            lines.append(f"- {contribution.persona_id}: {note}")
    if turn_state.synthesis is not None:
        lines.extend(
            [
                "synthesis:",
                turn_state.synthesis.summary,
                "source_personas: "
                f"{', '.join(turn_state.synthesis.source_personas)}",
            ]
        )
    if discussion_note:
        lines.append(discussion_note.strip())
    return "\n".join(lines)
