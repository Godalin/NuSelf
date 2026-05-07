"""File-backed repository for user-visible memory entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from nuself.config import runtime_paths
from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEntry,
    MemoryObject,
    MemoryTypeRegistry,
    default_memory_type_registry,
    now_iso,
)


class MemoryEntryNotFound(KeyError):
    """Raised when a memory entry does not exist."""


class MemoryCandidateNotFound(KeyError):
    """Raised when a memory candidate does not exist."""


class MemoryEntryRepository:
    """Stores one JSON file per memory entry under private/memory/entries."""

    def __init__(self, project_root: Path | None = None, *, registry: MemoryTypeRegistry | None = None) -> None:
        self._paths = runtime_paths(project_root)
        self._entries_dir = self._paths.private_root / "memory" / "entries"
        self._registry = registry or default_memory_type_registry()

    @property
    def entries_dir(self) -> Path:
        return self._entries_dir

    def ensure(self) -> None:
        self._entries_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[MemoryEntry]:
        self.ensure()
        entries = [self._read_path(path) for path in sorted(self._entries_dir.glob("*.json"))]
        return sorted(entries, key=lambda entry: entry.updated_at, reverse=True)

    def search(self, query: str) -> list[MemoryEntry]:
        normalized = query.casefold()
        return [
            entry
            for entry in self.list()
            if normalized in entry.title.casefold()
            or normalized in entry.body.casefold()
            or any(normalized in tag.casefold() for tag in entry.tags)
        ]

    def get(self, entry_id: str) -> MemoryEntry:
        path = self._path_for(entry_id)
        if not path.exists():
            raise MemoryEntryNotFound(entry_id)
        return self._read_path(path)

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        self._registry.validate(entry.to_memory_object())
        self.ensure()
        path = self._path_for(entry.id)
        path.write_text(
            json.dumps(entry.to_wire(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return entry

    def save_object(self, memory: MemoryObject) -> MemoryObject:
        self._registry.validate(memory)
        self.save(MemoryEntry.from_memory_object(memory))
        return memory

    def delete(self, entry_id: str) -> None:
        path = self._path_for(entry_id)
        if not path.exists():
            raise MemoryEntryNotFound(entry_id)
        path.unlink()

    def reindex(self) -> Path:
        derived_dir = self._paths.private_root / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        index_path = derived_dir / "memory_index.json"
        index = [
            {
                "id": entry.id,
                "type": entry.type,
                "title": entry.title,
                "tags": entry.tags,
                "updated_at": entry.updated_at,
            }
            for entry in self.list()
        ]
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return index_path

    def _path_for(self, entry_id: str) -> Path:
        if "/" in entry_id or entry_id in {"", ".", ".."}:
            raise ValueError(f"invalid memory entry id: {entry_id}")
        return self._entries_dir / f"{entry_id}.json"

    def _read_path(self, path: Path) -> MemoryEntry:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"memory entry file must contain an object: {path}")
        data = cast(dict[str, object], raw)
        if "payload" in data:
            return MemoryEntry.from_memory_object(MemoryObject.from_wire(data))
        return MemoryEntry.from_wire(data)


class MemoryCandidateRepository:
    """Stores reviewable memory candidates under private/memory/candidates."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        entry_repository: MemoryEntryRepository | None = None,
    ) -> None:
        self._paths = runtime_paths(project_root)
        self._candidates_dir = self._paths.private_root / "memory" / "candidates"
        self._entry_repository = entry_repository or MemoryEntryRepository(project_root)

    @property
    def candidates_dir(self) -> Path:
        return self._candidates_dir

    def ensure(self) -> None:
        self._candidates_dir.mkdir(parents=True, exist_ok=True)

    def list(self, *, include_reviewed: bool = False) -> list[MemoryCandidate]:
        self.ensure()
        candidates = [self._read_path(path) for path in sorted(self._candidates_dir.glob("*.json"))]
        if not include_reviewed:
            candidates = [candidate for candidate in candidates if candidate.review_state == "pending"]
        return sorted(candidates, key=lambda candidate: candidate.updated_at, reverse=True)

    def get(self, candidate_id: str) -> MemoryCandidate:
        path = self._path_for(candidate_id)
        if not path.exists():
            raise MemoryCandidateNotFound(candidate_id)
        return self._read_path(path)

    def save(self, candidate: MemoryCandidate) -> MemoryCandidate:
        self.ensure()
        path = self._path_for(candidate.id)
        path.write_text(
            json.dumps(candidate.to_wire(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return candidate

    def accept(self, candidate_id: str) -> MemoryEntry:
        candidate = self.get(candidate_id)
        if candidate.review_state != "pending":
            raise ValueError(f"candidate is already {candidate.review_state}: {candidate_id}")
        if candidate.action == "delete":
            if candidate.target_entry_id is None:
                raise ValueError(f"delete candidate requires target_entry_id: {candidate_id}")
            entry = self._entry_repository.get(candidate.target_entry_id)
            self._entry_repository.delete(candidate.target_entry_id)
            self._entry_repository.reindex()
            self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry.id))
            return entry
        if candidate.action in {"update", "merge"}:
            if candidate.target_entry_id is None:
                raise ValueError(f"{candidate.action} candidate requires target_entry_id: {candidate_id}")
            return self.merge(candidate_id, candidate.target_entry_id)
        entry = self._entry_repository.save(candidate.to_entry())
        self._entry_repository.reindex()
        self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry.id))
        return entry

    def reject(self, candidate_id: str) -> MemoryCandidate:
        candidate = self.get(candidate_id)
        rejected = candidate.with_updates(review_state="rejected")
        self.save(rejected)
        return rejected

    def merge(self, candidate_id: str, entry_id: str) -> MemoryEntry:
        candidate = self.get(candidate_id)
        if candidate.review_state != "pending":
            raise ValueError(f"candidate is already {candidate.review_state}: {candidate_id}")
        existing = self._entry_repository.get(entry_id)
        merged = MemoryEntry(
            type=existing.type,
            title=candidate.title,
            body=candidate.body,
            tags=candidate.tags or existing.tags,
            source_refs=[*existing.source_refs, *candidate.source_refs],
            confidence=candidate.confidence,
            privacy=existing.privacy,
            review_state="draft",
            id=existing.id,
            created_at=existing.created_at,
            updated_at=now_iso(),
            revisit_at=existing.revisit_at,
            observed_at=candidate.observed_at or existing.observed_at,
            valid_from=candidate.valid_from or existing.valid_from,
            valid_until=candidate.valid_until or existing.valid_until,
            temporal_note=candidate.temporal_note or existing.temporal_note,
            supersedes=[*existing.supersedes, *candidate.supersedes],
            related_memory_ids=[*existing.related_memory_ids, *candidate.related_memory_ids],
            evidence=[*existing.evidence, *candidate.evidence],
        )
        self._entry_repository.save(merged)
        self._entry_repository.reindex()
        self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry_id))
        return merged

    def _path_for(self, candidate_id: str) -> Path:
        if "/" in candidate_id or candidate_id in {"", ".", ".."}:
            raise ValueError(f"invalid memory candidate id: {candidate_id}")
        return self._candidates_dir / f"{candidate_id}.json"

    def _read_path(self, path: Path) -> MemoryCandidate:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"memory candidate file must contain an object: {path}")
        return MemoryCandidate.from_wire(cast(dict[str, object], raw))
