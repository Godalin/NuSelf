"""Trace subsystem service interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nuself.trace.model import ThoughtTrace, TraceKind, TraceLink, TraceVisibility
from nuself.trace.repository import TraceRepository, TraceVisibilityFilter

if TYPE_CHECKING:
    from nuself.reason.model import ReasoningStep, ReasoningThread


class TraceRecorder:
    """Service interface for other subsystems to create traces and links."""

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    def _record(
        self,
        *,
        kind: TraceKind,
        title: str,
        summary: str,
        inputs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        derived_from: list[str] | None = None,
        outputs: list[str] | None = None,
        participants: list[str] | None = None,
        decision_points: list[str] | None = None,
        conversation_id: str | None = None,
        visibility: TraceVisibility = "private",
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        trace = ThoughtTrace(
            kind=kind,
            title=title,
            summary=summary,
            inputs=inputs or [],
            evidence_refs=evidence_refs or [],
            derived_from=derived_from or [],
            outputs=outputs or [],
            participants=participants or [],
            decision_points=decision_points or [],
            conversation_id=conversation_id,
            visibility=visibility,
            metadata=metadata or {},
        )
        return self._repository.save_trace(trace)

    def record_chat_turn(
        self,
        *,
        title: str,
        summary: str,
        user_input: str,
        assistant_output: str,
        conversation_id: str,
        evidence_refs: list[str] | None = None,
        participants: list[str] | None = None,
        decision_points: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="chat_turn",
            title=title,
            summary=summary,
            inputs=[user_input],
            outputs=[assistant_output],
            evidence_refs=evidence_refs or [],
            participants=participants or [],
            decision_points=decision_points or [],
            conversation_id=conversation_id,
            metadata=metadata or {},
        )

    def record_reason_thread_created(
        self,
        *,
        thread: ReasoningThread,
        source_trace_ids: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="reason_thread",
            title=f"Reason thread created: {_short(thread.topic)}",
            summary=f"Created a durable reasoning thread for: {thread.topic}",
            inputs=[thread.topic],
            evidence_refs=[],
            derived_from=source_trace_ids or [],
            outputs=[f"reason:{thread.id}"],
            participants=["reason"],
            decision_points=["User-approved long-run reasoning thread creation."],
            visibility="private",
            metadata={"thread_id": thread.id, "status": thread.status, "mandates": list(thread.mandates_data), **(metadata or {})},
        )

    def record_reason_step(
        self,
        *,
        thread: ReasoningThread,
        step: ReasoningStep,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="reason_step",
            title=f"Reason step: {_short(thread.topic)}",
            summary=step.summary,
            inputs=[f"reason:{thread.id}"],
            evidence_refs=list(step.evidence_refs),
            outputs=[f"reason:{thread.id}", f"reason_step:{step.id}"],
            participants=["reason"],
            decision_points=[f"{step.terminal_status}: {step.terminal_reason}"] if step.terminal_status != "continue" and step.terminal_reason else [],
            visibility="private",
            metadata={
                "thread_id": thread.id,
                "step_id": step.id,
                "step_kind": step.kind,
                **(metadata or {}),
            },
        )

    def record_reflection_created(
        self,
        *,
        reflection_id: str,
        title: str,
        body: str,
        candidate_type: str,
        composite_score: float,
        discussion_approved: bool | None,
        evidence_refs: list[str] | None = None,
        conversation_id: str | None = None,
        decision_points: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="reflection",
            title=title,
            summary=body,
            outputs=[f"reflection:{reflection_id}"],
            evidence_refs=evidence_refs or [],
            participants=["reflection"],
            conversation_id=conversation_id,
            decision_points=decision_points or [],
            visibility="private",
            metadata={
                "candidate_type": candidate_type,
                "composite_score": composite_score,
                "discussion_approved": discussion_approved,
                **(metadata or {}),
            },
        )

    def record_memory_update(
        self,
        *,
        memory_id: str,
        title: str,
        summary: str,
        memory_type: str,
        action: str,
        confidence: float,
        source_ref: str,
        source_trace_id: str | None = None,
        participants: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        evidence_refs = [source_ref]
        if source_trace_id:
            evidence_refs.append(f"trace:{source_trace_id}")
        return self._record(
            kind="memory_update",
            title=title,
            summary=summary,
            outputs=[f"memory:{memory_id}"],
            evidence_refs=evidence_refs,
            participants=participants or ["memory_curator"],
            decision_points=[f"curator action: {action} (confidence={confidence:.2f}, type={memory_type})"],
            visibility="private",
            metadata={
                "memory_type": memory_type,
                "action": action,
                "confidence": confidence,
                **(metadata or {}),
            },
        )

    def record_persona_prompt_created(
        self,
        *,
        persona_prompt_id: str,
        name: str,
        participants: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="persona_prompt_created",
            title=f"Persona prompt: {name}",
            summary=f"Created or updated dynamic thinking persona: {name}",
            outputs=[f"persona_prompt:{persona_prompt_id}"],
            participants=participants or ["chat"],
            visibility="private",
            metadata={"prompt_id": persona_prompt_id, "name": name, **(metadata or {})},
        )

    def record_persona_disabled(
        self,
        *,
        persona_prompt_id: str,
        name: str,
        participants: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="persona_disabled",
            title=f"Persona disabled: {name}",
            summary=f"Disabled dynamic thinking persona: {name}",
            outputs=[f"persona_prompt:{persona_prompt_id}"],
            participants=participants or ["cli"],
            visibility="private",
            metadata={"prompt_id": persona_prompt_id, "name": name, **(metadata or {})},
        )

    def record_persona_enabled(
        self,
        *,
        persona_prompt_id: str,
        name: str,
        participants: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        return self._record(
            kind="persona_enabled",
            title=f"Persona enabled: {name}",
            summary=f"Enabled dynamic thinking persona: {name}",
            outputs=[f"persona_prompt:{persona_prompt_id}"],
            participants=participants or ["cli"],
            visibility="private",
            metadata={"prompt_id": persona_prompt_id, "name": name, **(metadata or {})},
        )

    def record_reflection_promoted(
        self,
        *,
        reflection_id: str,
        reflection_title: str,
        thread: ReasoningThread,
        metadata: dict[str, object] | None = None,
    ) -> ThoughtTrace:
        trace = self._record(
            kind="promotion",
            title=f"Reflection promoted: {_short(reflection_title)}",
            summary=f"Promoted reflection into reason thread: {thread.topic}",
            inputs=[f"reflection:{reflection_id}"],
            evidence_refs=[f"reflection:{reflection_id}", *thread.evidence_refs],
            outputs=[f"reason:{thread.id}"],
            participants=["reflection", "reason"],
            decision_points=["Reflection selected for durable long-run reasoning."],
            visibility="private",
            metadata={"reflection_id": reflection_id, "thread_id": thread.id, **(metadata or {})},
        )
        self._repository.save_link(
            TraceLink(
                source_id=f"reflection:{reflection_id}",
                target_id=f"reason:{thread.id}",
                relation="triggered",
                summary="Reflection promotion created this reason thread.",
            )
        )
        return trace


class TraceQueryService:
    """Read/query interface for trace records."""

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    def list_traces(
        self,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        return self._repository.list_traces(kind=kind, visibility=visibility)

    def show_trace(self, id_or_index: str) -> ThoughtTrace:
        return self._repository.resolve_trace(id_or_index)

    def search_traces(
        self,
        query: str,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        return self._repository.search_traces(query, kind=kind, visibility=visibility)

    def traces_for_artifact(
        self,
        artifact_ref: str,
        *,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        return self._repository.traces_for_artifact(artifact_ref, visibility=visibility)

    def links_for(self, trace_id: str) -> list[TraceLink]:
        return self._repository.links_for(trace_id)

    def links_for_artifact(self, artifact_ref: str) -> list[TraceLink]:
        return self._repository.links_for_artifact(artifact_ref)

def _short(value: str, limit: int = 80) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."
