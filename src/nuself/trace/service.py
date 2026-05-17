"""Trace subsystem service interfaces."""

from __future__ import annotations

from pathlib import Path

from nuself.trace.domain import ThoughtTrace, TraceKind, TraceLink, TraceRelation, TraceVisibility
from nuself.trace.repository import TraceRepository, TraceVisibilityFilter


class TraceRecorder:
    """Service interface for other subsystems to create traces and links."""

    def __init__(self, project_root: Path | None = None, repository: TraceRepository | None = None) -> None:
        self._repository = repository or TraceRepository(project_root)

    def record(
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
        thread_id: str | None = None,
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
            thread_id=thread_id,
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
        thread_id: str,
        evidence_refs: list[str] | None = None,
        participants: list[str] | None = None,
        decision_points: list[str] | None = None,
    ) -> ThoughtTrace:
        return self.record(
            kind="chat_turn",
            title=title,
            summary=summary,
            inputs=[user_input],
            outputs=[assistant_output],
            evidence_refs=evidence_refs or [],
            participants=participants or [],
            decision_points=decision_points or [],
            thread_id=thread_id,
        )

    def link(self, source_id: str, target_id: str, relation: TraceRelation, summary: str) -> TraceLink:
        return self._repository.save_link(
            TraceLink(source_id=source_id, target_id=target_id, relation=relation, summary=summary)
        )


class TraceQueryService:
    """Read/query interface for trace records."""

    def __init__(self, project_root: Path | None = None, repository: TraceRepository | None = None) -> None:
        self._repository = repository or TraceRepository(project_root)

    def list_traces(
        self,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        return self._repository.list_traces(kind=kind, visibility=visibility)

    def show_trace(self, id_or_index: str, *, by_index: bool = False) -> ThoughtTrace:
        return self._repository.resolve_trace(id_or_index, by_index=by_index)

    def search_traces(
        self,
        query: str,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        return self._repository.search_traces(query, kind=kind, visibility=visibility)

    def links_for(self, trace_id: str) -> list[TraceLink]:
        return self._repository.links_for(trace_id)
