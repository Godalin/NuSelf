"""File-backed repository for reflection entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from nuself.config import runtime_paths
from nuself.runtime.observability import decode_observed_record
from nuself.storage import StorageBackend, auto_backend


@dataclass(frozen=True)
class ReflectionEntry:
    """A reflection idea produced by the proactive scheduler."""

    id: str
    title: str
    body: str
    candidate_type: str
    confidence: float
    novelty: float
    urgency: float
    interruption_cost: float
    composite_score: float
    status: Literal["pending", "dismissed", "archived"]
    discussion_approved: bool | None
    discussion_trace: tuple[str, ...]
    deep_link: str
    created_at: str
    reviewed_at: str | None

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "candidate_type": self.candidate_type,
            "confidence": self.confidence,
            "novelty": self.novelty,
            "urgency": self.urgency,
            "interruption_cost": self.interruption_cost,
            "composite_score": self.composite_score,
            "status": self.status,
            "discussion_approved": self.discussion_approved,
            "discussion_trace": list(self.discussion_trace),
            "deep_link": self.deep_link,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReflectionEntry:
        trace = data.get("discussion_trace", [])
        confidence_raw = data.get("confidence", 0.5)
        novelty_raw = data.get("novelty", 0.5)
        urgency_raw = data.get("urgency", 0.3)
        interruption_raw = data.get("interruption_cost", 0.2)
        composite_raw = data.get("composite_score", 0.0)
        return cls(
            id=cast(str, data["id"]),
            title=cast(str, data["title"]),
            body=cast(str, data["body"]),
            candidate_type=cast(str, data.get("candidate_type", "question")),
            confidence=float(confidence_raw),  # type: ignore[arg-type]
            novelty=float(novelty_raw),  # type: ignore[arg-type]
            urgency=float(urgency_raw),  # type: ignore[arg-type]
            interruption_cost=float(interruption_raw),  # type: ignore[arg-type]
            composite_score=float(composite_raw),  # type: ignore[arg-type]
            status=cast(Literal["pending", "dismissed", "archived"], data.get("status", "pending")),
            discussion_approved=cast(bool | None, data.get("discussion_approved")),
            discussion_trace=tuple(cast(list[str], trace)),
            deep_link=cast(str, data.get("deep_link", "")),
            created_at=cast(str, data.get("created_at", "")),
            reviewed_at=cast(str | None, data.get("reviewed_at")),
        )

    def with_status(self, status: Literal["pending", "dismissed", "archived"]) -> ReflectionEntry:
        reviewed_at = datetime.now(UTC).isoformat() if status != "pending" else None
        return ReflectionEntry(
            id=self.id,
            title=self.title,
            body=self.body,
            candidate_type=self.candidate_type,
            confidence=self.confidence,
            novelty=self.novelty,
            urgency=self.urgency,
            interruption_cost=self.interruption_cost,
            composite_score=self.composite_score,
            status=status,
            discussion_approved=self.discussion_approved,
            discussion_trace=self.discussion_trace,
            deep_link=self.deep_link,
            created_at=self.created_at,
            reviewed_at=reviewed_at,
        )


class ReflectionEntryNotFound(ValueError):
    """Raised when a reflection entry does not exist."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"reflection entry not found: {entry_id}")


class ReflectionRepository:
    """Store reflection ideas in private/reflections/."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        be = backend if backend is not None else auto_backend(project_root)
        self._col = be.collection("reflection_entries")
        self._paths = runtime_paths(project_root)

    def list(self, status: str | None = None) -> list[ReflectionEntry]:
        entries: list[ReflectionEntry] = []
        for wire in self._col.list():
            entry = decode_observed_record(
                wire,
                ReflectionEntry.from_wire,
                component="reflection",
                collection="reflection_entries",
                project_root=self._paths.project_root,
            )
            if entry is None:
                continue
            if status is None or entry.status == status:
                entries.append(entry)
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def get(self, entry_id: str) -> ReflectionEntry:
        wire = self._col.get(entry_id)
        if wire is None:
            raise ReflectionEntryNotFound(entry_id)
        return ReflectionEntry.from_wire(wire)

    def add(self, entry: ReflectionEntry) -> ReflectionEntry:
        self._col.put(entry.id, entry.to_wire())
        return entry

    def update(self, entry: ReflectionEntry) -> ReflectionEntry:
        return self.add(entry)

    def dismiss(self, entry_id: str) -> ReflectionEntry:
        entry = self.get(entry_id)
        updated = entry.with_status("dismissed")
        self.add(updated)
        return updated

    def archive(self, entry_id: str) -> ReflectionEntry:
        entry = self.get(entry_id)
        updated = entry.with_status("archived")
        self.add(updated)
        return updated
