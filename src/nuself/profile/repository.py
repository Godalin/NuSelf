"""File-backed repository for derived profile items."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
from pathlib import Path
from nuself.config import runtime_paths
from nuself.domain.memory import MemoryCandidate, merge_relations, now_iso
from nuself.domain.profile import ProfileItem
from nuself.storage import StorageBackend, create_file_backend


def empty_str_counts() -> dict[str, int]:
    return {}


@dataclass(frozen=True)
class ProfileStats:
    """Compact summary of derived profile state."""

    items_total: int
    items_by_type: dict[str, int] = field(default_factory=empty_str_counts)
    items_with_evidence: int = 0


@dataclass(frozen=True)
class ProfileSearchFilters:
    """Deterministic filters for profile search."""

    type: str | None = None
    tag: str | None = None
    observed_from: str | None = None
    observed_to: str | None = None
    valid_on: str | None = None


class ProfileItemNotFound(KeyError):
    """Raised when a profile item does not exist."""


class ProfileItemRepository:
    """Stores one JSON file per derived profile item under private/profile/items."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        be = backend if backend is not None else create_file_backend(project_root)
        self._col = be.collection("profile_items")
        self._paths = runtime_paths(project_root)

    def list(self) -> list[ProfileItem]:
        items: list[ProfileItem] = []
        for wire in self._col.list():
            try:
                items.append(ProfileItem.from_wire(wire))
            except (ValueError, KeyError):
                pass
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def search(self, query: str, filters: ProfileSearchFilters | None = None) -> list[ProfileItem]:
        normalized = query.casefold()
        return [item for item in self.list() if _matches_text(item, normalized) and _matches_filters(item, filters)]

    def get(self, item_id: str) -> ProfileItem:
        wire = self._col.get(item_id)
        if wire is None:
            raise ProfileItemNotFound(item_id)
        return ProfileItem.from_wire(wire)

    def save(self, item: ProfileItem) -> ProfileItem:
        self._col.put(item.id, item.to_wire())
        return item

    def delete(self, item_id: str) -> None:
        wire = self._col.get(item_id)
        if wire is None:
            raise ProfileItemNotFound(item_id)
        self._col.delete(item_id)

    def merge(self, candidate: MemoryCandidate, item_id: str) -> ProfileItem:
        existing = self.get(item_id)
        merged = ProfileItem(
            type=existing.type,
            title=candidate.title,
            body=candidate.body,
            tags=candidate.tags or existing.tags,
            source_refs=[*existing.source_refs, *candidate.source_refs],
            confidence=candidate.confidence,
            privacy=existing.privacy,
            id=existing.id,
            created_at=existing.created_at,
            updated_at=now_iso(),
            observed_at=candidate.observed_at or existing.observed_at,
            valid_from=candidate.valid_from or existing.valid_from,
            valid_until=candidate.valid_until or existing.valid_until,
            temporal_note=candidate.temporal_note or existing.temporal_note,
            relations=merge_relations(existing.relations, candidate.relations),
            evidence=[*existing.evidence, *candidate.evidence],
        )
        self.save(merged)
        return merged

    def accept(self, candidate: MemoryCandidate) -> ProfileItem:
        item = ProfileItem.from_candidate(candidate)
        self.save(item)
        return item

    def reindex(self) -> Path:
        derived_dir = self._paths.private_root / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        index_path = derived_dir / "profile_index.json"
        index = [
            {
                "id": item.id,
                "type": item.type,
                "title": item.title,
                "tags": item.tags,
                "source_refs": item.source_refs,
                "updated_at": item.updated_at,
            }
            for item in self.list()
        ]
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return index_path


def profile_stats(project_root: Path | None = None) -> ProfileStats:
    items = ProfileItemRepository(project_root).list()
    return ProfileStats(
        items_total=len(items),
        items_by_type=_counts(item.type for item in items),
        items_with_evidence=sum(1 for item in items if item.evidence),
    )


def _counts(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _matches_text(item: ProfileItem, normalized_query: str) -> bool:
    if normalized_query == "":
        return True
    return (
        normalized_query in item.title.casefold()
        or normalized_query in item.body.casefold()
        or any(normalized_query in tag.casefold() for tag in item.tags)
        or any(normalized_query in source_ref.casefold() for source_ref in item.source_refs)
    )


def _matches_filters(item: ProfileItem, filters: ProfileSearchFilters | None) -> bool:
    if filters is None:
        return True
    if filters.type is not None and item.type != filters.type:
        return False
    if filters.tag is not None and filters.tag not in item.tags:
        return False
    if filters.observed_from is not None and (item.observed_at is None or item.observed_at < filters.observed_from):
        return False
    if filters.observed_to is not None and (item.observed_at is None or item.observed_at > filters.observed_to):
        return False
    if filters.valid_on is not None:
        if item.valid_from is not None and item.valid_from > filters.valid_on:
            return False
        if item.valid_until is not None and item.valid_until < filters.valid_on:
            return False
    return True