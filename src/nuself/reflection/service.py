"""Reflection service operations."""

from __future__ import annotations

from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.reason.model import ReasoningThread
from nuself.reflection.contracts import (
    ReasonThreadStarter,
    ReflectionPromotionRecorder,
)
from nuself.reflection.organizer import (
    ReflectionOrganizationResult,
    ReflectionOrganizer,
)
from nuself.reflection.repository import ReflectionEntry, ReflectionEntryNotFound, ReflectionRepository
from nuself.runtime.diagnostics import diagnostic_exception_message


class ReflectionService:
    """User-intent operations for reflection entries."""

    def __init__(
        self,
        repository: ReflectionRepository,
        reason_service: ReasonThreadStarter,
        trace_recorder: ReflectionPromotionRecorder,
        organizer: ReflectionOrganizer,
    ) -> None:
        self._repository = repository
        self._reason_service = reason_service
        self._trace_recorder = trace_recorder
        self._organizer = organizer

    def list_entries(
        self,
        *,
        status: str | None = None,
    ) -> list[ReflectionEntry]:
        return self._repository.list(status=status)

    def show_entry(self, id_or_index: str) -> ReflectionEntry:
        return self._resolve_entry(id_or_index)

    def dismiss_entry(self, id_or_index: str) -> ReflectionEntry:
        entry = self._resolve_entry(id_or_index)
        return self._repository.save(entry.with_status("dismissed"))

    def archive_entry(self, id_or_index: str) -> ReflectionEntry:
        entry = self._resolve_entry(id_or_index)
        return self._repository.save(entry.with_status("archived"))

    def organize_pending(self) -> ReflectionOrganizationResult:
        return self._organizer.organize_pending()

    def promote_to_reason(self, id_or_index: str) -> ReasoningThread:
        entry = self.show_entry(id_or_index)
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
