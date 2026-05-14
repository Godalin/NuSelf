"""File-backed repository for reflection entries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from nuself.config import runtime_paths


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

    def __init__(self, project_root: Path | None = None) -> None:
        paths = runtime_paths(project_root)
        self._reflections_dir = paths.private_root / "reflections"

    def ensure(self) -> None:
        self._reflections_dir.mkdir(parents=True, exist_ok=True)

    def list(self, status: str | None = None) -> list[ReflectionEntry]:
        self.ensure()
        entries: list[ReflectionEntry] = []
        for path in sorted(self._reflections_dir.glob("*.json")):
            entry = self._read_path(path)
            if status is None or entry.status == status:
                entries.append(entry)
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def get(self, entry_id: str) -> ReflectionEntry:
        path = self._path_for(entry_id)
        if not path.exists():
            raise ReflectionEntryNotFound(entry_id)
        return self._read_path(path)

    def add(self, entry: ReflectionEntry) -> ReflectionEntry:
        self.ensure()
        path = self._path_for(entry.id)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(entry.to_wire(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
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

    def _path_for(self, entry_id: str) -> Path:
        if "/" in entry_id or entry_id in {"", ".", ".."}:
            raise ValueError(f"invalid entry id: {entry_id}")
        return self._reflections_dir / f"{entry_id}.json"

    def _read_path(self, path: Path) -> ReflectionEntry:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"invalid reflection entry: {path}")
        return ReflectionEntry.from_wire(cast(dict[str, object], raw))
