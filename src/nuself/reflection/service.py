"""Reflection service operations."""

from __future__ import annotations

from pathlib import Path

from nuself.reason.domain import ReasoningThread
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
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
        self._trace_recorder = trace_recorder or TraceRecorder(project_root)

    def promote_to_reason(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        entry = self._resolve_entry(id_or_index, by_index=by_index)
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

    def _resolve_entry(self, id_or_index: str, *, by_index: bool = False) -> ReflectionEntry:
        if not by_index:
            return self._repository.get(id_or_index)
        try:
            index = int(id_or_index)
        except ValueError as exc:
            raise ValueError(f"invalid reflection index: {id_or_index}") from exc
        entries = self._repository.list()
        if index < 0 or index >= len(entries):
            raise ValueError(f"invalid reflection index {index}. Valid range: 0-{len(entries) - 1}")
        return entries[index]
