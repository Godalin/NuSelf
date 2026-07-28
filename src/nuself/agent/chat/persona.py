"""Persona consultation orchestration for the chat runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nuself.domain.proactive import IdeaCandidate
from nuself.llm import LangChainLLMEndpoint
from nuself.logs import LogLevel
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.persona import (
    AgentBackedActivationPolicy,
    AgentBackedPersonaNode,
    AgentBackedSynthesizerNode,
    PersonaDefinition,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
    SharedPersonaDiscussionService,
    load_persona_definitions,
    persona_graph_agents,
)
from nuself.runtime.context import current_runtime_context
from nuself.runtime.observability import (
    format_exception_chain,
    write_observed_log_event,
)


class ConversationPersonaOrchestrator:
    """Runs bounded selves consultation and optional competitive discussion."""

    def __init__(
        self,
        *,
        project_root: Path | None,
        langchain_models: tuple[LangChainLLMEndpoint, ...],
        language_preference: str,
        memory_query_service: MemoryQueryService,
    ) -> None:
        self._project_root = project_root
        self._memory_query_service = memory_query_service
        self._persona_definitions = load_persona_definitions(project_root)
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
        thread_id = current_runtime_context().thread_id or "default"
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
            thread_id=thread_id,
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
            thread_id=thread_id,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
        discussion_note = self._run_discussion(
            topic=topic,
            thread_id=thread_id,
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
        thread_id: str,
        trigger: str,
        turn_state: PersonaTurnState,
        should_escalate: bool,
    ) -> str:
        if not should_escalate:
            return ""
        try:
            result = self._discussion_service.discuss(
                self._build_candidate(
                    thread_id=thread_id,
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
                ),
                on_trace_entry=lambda entry: self._write_discussion_step_log(
                    thread_id,
                    trigger,
                    entry,
                ),
            )
            self._write_audit(
                "persona_discussion",
                f"chat-triggered discussion: {result.reason}",
                thread_id=thread_id,
                status=trigger,
                metadata={
                    "winner_persona_ids": list(result.winner_persona_ids),
                    "emergent_persona_ids": list(
                        result.emergent_persona_ids
                    ),
                    "blocking_vetos": list(result.blocking_vetos),
                    "reason": result.reason,
                    "discussion_steps": len(result.discussion_trace),
                },
            )
            return f"\nDiscussion result: {result.reason}"
        except Exception as exc:
            self._write_audit(
                "persona_discussion_failure",
                str(exc),
                thread_id=thread_id,
                level="error",
                error=str(exc),
                metadata={"original_error": format_exception_chain(exc)},
            )
            return f"\nDiscussion failed: {exc}"

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
        thread_id: str,
        trigger: str,
    ) -> None:
        self._write_audit(
            "persona_summary",
            _compact_summary(turn_state),
            thread_id=thread_id,
            status=trigger,
            metadata={
                "persona_count": len(turn_state.contributions),
                "has_synthesis": turn_state.synthesis is not None,
            },
        )

    def _write_host_decision_log(
        self,
        *,
        thread_id: str,
        should_escalate: bool,
        escalation_reason: str,
    ) -> None:
        self._write_audit(
            "host_discussion_decision",
            escalation_reason,
            thread_id=thread_id,
            status="approved" if should_escalate else "skipped",
            metadata={
                "should_escalate": should_escalate,
                "escalation_reason": escalation_reason,
            },
        )

    def _write_discussion_step_log(
        self,
        thread_id: str,
        trigger: str,
        entry: str,
    ) -> None:
        self._write_audit(
            "persona_discussion_step",
            "",
            thread_id=thread_id,
            status=trigger,
            metadata={"discussion_trace": [entry]},
        )

    def _write_audit(
        self,
        event: str,
        message: str,
        *,
        thread_id: str,
        status: str | None = None,
        level: LogLevel = "info",
        error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        failure_metadata: dict[str, object] = {
            "event": event,
            "thread_id": thread_id,
        }
        if metadata is not None and "original_error" in metadata:
            failure_metadata["original_error"] = metadata["original_error"]
        write_observed_log_event(
            "persona",
            event,
            message,
            project_root=self._project_root,
            thread_id=thread_id,
            status=status,
            level=level,
            error=error,
            metadata=metadata,
            failure_event=f"{event}_write_failed",
            failure_message=f"Failed to write {event} audit record",
            failure_metadata=failure_metadata,
        )

    @staticmethod
    def _build_candidate(
        *,
        thread_id: str,
        user_message: str,
        title: str,
        source_summary: str,
    ) -> IdeaCandidate:
        now = datetime.now(UTC)
        return IdeaCandidate(
            id=f"chat-{thread_id}-{int(now.timestamp())}",
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
            suggested_thread_id=thread_id,
            source_summary=source_summary,
            created_at=now.isoformat(),
        )


def _compact_summary(turn_state: PersonaTurnState) -> str:
    parts: list[str] = []
    for contribution in turn_state.contributions:
        note = contribution.notes[0] if contribution.notes else ""
        snippet = note if len(note) <= 140 else f"{note[:137]}..."
        parts.append(f"{contribution.persona_id}: {snippet}")
    if turn_state.synthesis is not None:
        summary = turn_state.synthesis.summary
        snippet = summary if len(summary) <= 140 else f"{summary[:137]}..."
        parts.append(f"synthesizer_self: {snippet}")
    return "\n".join(parts) if parts else "(no persona contributions)"


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
