"""Reflection service operations."""

from __future__ import annotations

from pathlib import Path

from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.reason.domain import ReasoningThread
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionEntry, ReflectionEntryNotFound, ReflectionRepository
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.storage import get_default_backend
from nuself.trace.composition import build_trace_recorder
from nuself.trace.service import TraceRecorder


class ReflectionService:
    """User-intent operations for reflection entries."""

    def __init__(
        self,
        project_root: Path | None = None,
        repository: ReflectionRepository | None = None,
        reason_service: ReasonService | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self._project_root = project_root
        self._repository = repository or ReflectionRepository(project_root)
        self._reason_service = reason_service or ReasonService(project_root)
        self._trace_recorder = trace_recorder or build_trace_recorder(
            project_root,
            backend=get_default_backend(project_root),
        )

    def promote_to_reason(self, id_or_index: str) -> ReasoningThread:
        entry = self._resolve_entry(id_or_index)
        if entry.status != "pending":
            raise RuntimeError(f"Cannot promote reflection {entry.id}: status is '{entry.status}', expected 'pending'")

        thread = self._reason_service.start_thread(
            entry.title,
            working_summary=entry.body,
            evidence_refs=(f"reflection:{entry.id}",),
        )
        self._trace_recorder.record_reflection_promoted(
            reflection_id=entry.id,
            reflection_title=entry.title,
            thread=thread,
            metadata={
                "candidate_type": entry.candidate_type,
                "composite_score": entry.composite_score,
            },
        )
        return thread

    def _resolve_entry(self, id_or_index: str) -> ReflectionEntry:
        try:
            return self._repository.get(id_or_index)
        except ReflectionEntryNotFound:
            pass
        entries = self._repository.list()
        try:
            entry = resolve_visible_item(id_or_index, entries, label="reflection")
        except VisibleHandleError as exc:
            raise ValueError(diagnostic_exception_message(exc)) from exc
        if entry is None:
            raise ValueError(f"invalid reflection index: {id_or_index}")
        return entry
