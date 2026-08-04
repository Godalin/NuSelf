"""User-intent operations for reviewing memory candidates."""

from __future__ import annotations

from nuself.memory.model import MemoryCandidate, MemoryEntry
from nuself.memory.repository import MemoryCandidateRepository
from nuself.profile.model import ProfileItem


class MemoryCandidateService:
    """Review and promote candidates without exposing persistence."""

    def __init__(self, repository: MemoryCandidateRepository) -> None:
        self._repository = repository

    def list_candidates(
        self,
        *,
        include_reviewed: bool = False,
    ) -> list[MemoryCandidate]:
        return self._repository.list(include_reviewed=include_reviewed)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate:
        return self._repository.get(candidate_id)

    def accept(self, candidate_id: str) -> MemoryEntry | ProfileItem:
        return self._repository.accept(candidate_id)

    def reject(self, candidate_id: str) -> MemoryCandidate:
        return self._repository.reject(candidate_id)

    def edit(
        self,
        candidate_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
        observed_at: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        temporal_note: str | None = None,
    ) -> MemoryCandidate:
        return self._repository.edit(
            candidate_id,
            title=title,
            body=body,
            tags=tags,
            importance=importance,
            observed_at=observed_at,
            valid_from=valid_from,
            valid_until=valid_until,
            temporal_note=temporal_note,
        )

    def merge(
        self,
        candidate_id: str,
        entry_id: str,
    ) -> MemoryEntry | ProfileItem:
        return self._repository.merge(candidate_id, entry_id)

    def delete_candidate(self, candidate_id: str) -> None:
        self._repository.delete(candidate_id)
