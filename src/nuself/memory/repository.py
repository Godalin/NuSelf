"""File-backed repository for user-visible memory entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from nuself.config import runtime_paths
from nuself.domain.memory import MemoryEntry


class MemoryEntryNotFound(KeyError):
    """Raised when a memory entry does not exist."""


class MemoryEntryRepository:
    """Stores one JSON file per memory entry under private/memory/entries."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = runtime_paths(project_root)
        self._entries_dir = self._paths.private_root / "memory" / "entries"

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
        self.ensure()
        path = self._path_for(entry.id)
        path.write_text(
            json.dumps(entry.to_wire(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return entry

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
        return MemoryEntry.from_wire(cast(dict[str, object], raw))
