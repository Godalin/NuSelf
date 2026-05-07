"""File-backed repository for user-visible memory entries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import cast

from nuself.config import runtime_paths
from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEntry,
    MemoryObject,
    MemoryTypeRegistry,
    RelationDescriptor,
    RelationDescriptorRegistry,
    default_memory_type_registry,
    default_relation_descriptor_registry,
    now_iso,
)
from nuself.domain.profile import ProfileItem
from nuself.profile.repository import ProfileItemRepository


def empty_str_counts() -> dict[str, int]:
    return {}


@dataclass(frozen=True)
class MemorySearchFilters:
    """Deterministic filters for entry search."""

    type: str | None = None
    tag: str | None = None
    review_state: str | None = None
    observed_from: str | None = None
    observed_to: str | None = None
    valid_on: str | None = None


@dataclass(frozen=True)
class MemoryStats:
    """Compact summary of memory repository state."""

    entries_total: int
    candidates_total: int
    entries_by_type: dict[str, int] = field(default_factory=empty_str_counts)
    entries_by_review_state: dict[str, int] = field(default_factory=empty_str_counts)
    candidates_by_review_state: dict[str, int] = field(default_factory=empty_str_counts)
    entries_with_observed_at: int = 0
    entries_with_evidence: int = 0
    pending_candidates: int = 0


@dataclass(frozen=True)
class MemoryRelationIndexRecord:
    """One derived relation between durable memory entries."""

    source_id: str
    target_id: str
    relation: str
    inverse_relation: str | None
    symmetric: bool
    transitive: bool
    temporal_policy: str
    confidence_policy: str
    retrieval_rule: str
    source_type: str
    target_type: str | None
    source_title: str
    target_title: str | None
    target_exists: bool
    confidence: float
    source_updated_at: str


@dataclass(frozen=True)
class MemoryRelationFilters:
    """Deterministic filters for the derived relation index."""

    relation: str | None = None
    source_id: str | None = None
    target_id: str | None = None


class MemoryEntryNotFound(KeyError):
    """Raised when a memory entry does not exist."""


class MemoryCandidateNotFound(KeyError):
    """Raised when a memory candidate does not exist."""


class MemoryEntryRepository:
    """Stores one JSON file per memory entry under private/memory/entries."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        registry: MemoryTypeRegistry | None = None,
        relation_registry: RelationDescriptorRegistry | None = None,
    ) -> None:
        self._paths = runtime_paths(project_root)
        self._entries_dir = self._paths.private_root / "memory" / "entries"
        self._registry = registry or default_memory_type_registry()
        self._relation_registry = relation_registry or default_relation_descriptor_registry()

    @property
    def entries_dir(self) -> Path:
        return self._entries_dir

    def ensure(self) -> None:
        self._entries_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[MemoryEntry]:
        self.ensure()
        entries = [self._read_path(path) for path in sorted(self._entries_dir.glob("*.json"))]
        return sorted(entries, key=lambda entry: entry.updated_at, reverse=True)

    def search(self, query: str, filters: MemorySearchFilters | None = None) -> list[MemoryEntry]:
        normalized = query.casefold()
        return [
            entry
            for entry in self.list()
            if _matches_text(entry, normalized) and _matches_filters(entry, filters)
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
        entries = self.list()
        index = [
            {
                "id": entry.id,
                "type": entry.type,
                "title": entry.title,
                "tags": entry.tags,
                "updated_at": entry.updated_at,
            }
            for entry in entries
        ]
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._write_relation_index(derived_dir, entries)
        self._write_symbolic_graph(derived_dir, entries)
        return index_path

    def reindex_relations(self) -> Path:
        derived_dir = self._paths.private_root / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        return self._write_relation_index(derived_dir, self.list())

    def reindex_symbolic_graph(self) -> Path:
        derived_dir = self._paths.private_root / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        return self._write_symbolic_graph(derived_dir, self.list())

    def list_relations(self, filters: MemoryRelationFilters | None = None) -> list[MemoryRelationIndexRecord]:
        relation_path = self.relation_index_path
        if not relation_path.exists():
            self.reindex_relations()
        raw: object = json.loads(relation_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"relation index must contain a list: {relation_path}")
        records = [
            _relation_record_from_wire(cast(dict[str, object], item))
            for item in cast(list[object], raw)
            if isinstance(item, dict)
        ]
        return [record for record in records if _matches_relation_filters(record, filters)]

    @property
    def relation_index_path(self) -> Path:
        return self._paths.private_root / "derived" / "relation_index.json"

    def _write_relation_index(self, derived_dir: Path, entries: list[MemoryEntry]) -> Path:
        by_id = {entry.id: entry for entry in entries}
        relation_path = derived_dir / "relation_index.json"
        relations = [
            relation
            for entry in entries
            for relation in _relation_index_records(entry, by_id, self._relation_registry)
        ]
        relation_path.write_text(json.dumps(relations, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return relation_path

    def _write_symbolic_graph(self, derived_dir: Path, entries: list[MemoryEntry]) -> Path:
        by_id = {entry.id: entry for entry in entries}
        relations = [
            relation
            for entry in entries
            for relation in _relation_index_records(entry, by_id, self._relation_registry)
        ]
        graph_path = derived_dir / "symbolic_graph.json"
        graph = {
            "schema": "NuSelfSymbolicGraph/v1",
            "source": "private/memory/entries",
            "nodes": [_symbolic_node_record(entry) for entry in entries],
            "edges": [_symbolic_edge_record(relation) for relation in relations],
        }
        graph_path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return graph_path

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
        profile_repository: ProfileItemRepository | None = None,
    ) -> None:
        self._paths = runtime_paths(project_root)
        self._candidates_dir = self._paths.private_root / "memory" / "candidates"
        self._entry_repository = entry_repository or MemoryEntryRepository(project_root)
        self._profile_repository = profile_repository or ProfileItemRepository(project_root)

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

    def delete(self, candidate_id: str) -> None:
        path = self._path_for(candidate_id)
        if not path.exists():
            raise MemoryCandidateNotFound(candidate_id)
        path.unlink()

    def accept(self, candidate_id: str) -> MemoryEntry | ProfileItem:
        candidate = self.get(candidate_id)
        if candidate.review_state != "pending":
            raise ValueError(f"candidate is already {candidate.review_state}: {candidate_id}")
        if candidate.action == "delete":
            if candidate.target_entry_id is None:
                raise ValueError(f"delete candidate requires target_entry_id: {candidate_id}")
            entry = self._delete_target(candidate)
            self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry.id))
            return entry
        if candidate.action in {"update", "merge"}:
            if candidate.target_entry_id is None:
                raise ValueError(f"{candidate.action} candidate requires target_entry_id: {candidate_id}")
            return self.merge(candidate_id, candidate.target_entry_id)
        entry = self._save_target(candidate)
        self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry.id))
        return entry

    def reject(self, candidate_id: str) -> MemoryCandidate:
        candidate = self.get(candidate_id)
        rejected = candidate.with_updates(review_state="rejected")
        self.save(rejected)
        return rejected

    def merge(self, candidate_id: str, entry_id: str) -> MemoryEntry | ProfileItem:
        candidate = self.get(candidate_id)
        if candidate.review_state != "pending":
            raise ValueError(f"candidate is already {candidate.review_state}: {candidate_id}")
        merged = self._merge_target(candidate, entry_id)
        self.save(candidate.with_updates(review_state="accepted", target_entry_id=entry_id))
        return merged

    def _save_target(self, candidate: MemoryCandidate) -> MemoryEntry | ProfileItem:
        if candidate.type == "profile_fact":
            item = self._profile_repository.accept(candidate)
            self._profile_repository.reindex()
            return item
        entry = self._entry_repository.save(candidate.to_entry())
        self._entry_repository.reindex()
        return entry

    def _merge_target(self, candidate: MemoryCandidate, entry_id: str) -> MemoryEntry | ProfileItem:
        if candidate.type == "profile_fact":
            merged = self._profile_repository.merge(candidate, entry_id)
            self._profile_repository.reindex()
            return merged
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
        return merged

    def _delete_target(self, candidate: MemoryCandidate) -> MemoryEntry | ProfileItem:
        if candidate.type == "profile_fact":
            item = self._profile_repository.get(candidate.target_entry_id or "")
            self._profile_repository.delete(item.id)
            self._profile_repository.reindex()
            return item
        entry = self._entry_repository.get(candidate.target_entry_id or "")
        self._entry_repository.delete(candidate.target_entry_id or "")
        self._entry_repository.reindex()
        return entry

    def _path_for(self, candidate_id: str) -> Path:
        if "/" in candidate_id or candidate_id in {"", ".", ".."}:
            raise ValueError(f"invalid memory candidate id: {candidate_id}")
        return self._candidates_dir / f"{candidate_id}.json"

    def _read_path(self, path: Path) -> MemoryCandidate:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"memory candidate file must contain an object: {path}")
        return MemoryCandidate.from_wire(cast(dict[str, object], raw))


def memory_stats(project_root: Path | None = None) -> MemoryStats:
    """Return compact stats across durable entries and review candidates."""

    entries = MemoryEntryRepository(project_root).list()
    candidates = MemoryCandidateRepository(project_root).list(include_reviewed=True)
    return MemoryStats(
        entries_total=len(entries),
        candidates_total=len(candidates),
        entries_by_type=_counts(entry.type for entry in entries),
        entries_by_review_state=_counts(entry.review_state for entry in entries),
        candidates_by_review_state=_counts(candidate.review_state for candidate in candidates),
        entries_with_observed_at=sum(1 for entry in entries if entry.observed_at is not None),
        entries_with_evidence=sum(1 for entry in entries if entry.evidence),
        pending_candidates=sum(1 for candidate in candidates if candidate.review_state == "pending"),
    )


def _matches_text(entry: MemoryEntry, normalized_query: str) -> bool:
    if normalized_query == "":
        return True
    return (
        normalized_query in entry.title.casefold()
        or normalized_query in entry.body.casefold()
        or any(normalized_query in tag.casefold() for tag in entry.tags)
    )


def _matches_filters(entry: MemoryEntry, filters: MemorySearchFilters | None) -> bool:
    if filters is None:
        return True
    if filters.type is not None and entry.type != filters.type:
        return False
    if filters.tag is not None and filters.tag not in entry.tags:
        return False
    if filters.review_state is not None and entry.review_state != filters.review_state:
        return False
    if filters.observed_from is not None and (entry.observed_at is None or entry.observed_at < filters.observed_from):
        return False
    if filters.observed_to is not None and (entry.observed_at is None or entry.observed_at > filters.observed_to):
        return False
    if filters.valid_on is not None:
        if entry.valid_from is not None and entry.valid_from > filters.valid_on:
            return False
        if entry.valid_until is not None and entry.valid_until < filters.valid_on:
            return False
    return True


def _relation_index_records(
    entry: MemoryEntry,
    by_id: dict[str, MemoryEntry],
    registry: RelationDescriptorRegistry,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    supersedes = registry.require("supersedes")
    related_to = registry.require("related_to")
    for target_id in entry.supersedes:
        records.append(_relation_index_record(entry, target_id, supersedes, by_id))
    for target_id in entry.related_memory_ids:
        records.append(_relation_index_record(entry, target_id, related_to, by_id))
    return records


def _relation_index_record(
    entry: MemoryEntry,
    target_id: str,
    descriptor: RelationDescriptor,
    by_id: dict[str, MemoryEntry],
) -> dict[str, object]:
    target = by_id.get(target_id)
    return {
        "source_id": entry.id,
        "target_id": target_id,
        "relation": descriptor.name,
        "inverse_relation": descriptor.inverse,
        "symmetric": descriptor.symmetric,
        "transitive": descriptor.transitive,
        "temporal_policy": descriptor.temporal_policy,
        "confidence_policy": descriptor.confidence_policy,
        "retrieval_rule": descriptor.retrieval_rule,
        "source_type": entry.type,
        "target_type": target.type if target is not None else None,
        "source_title": entry.title,
        "target_title": target.title if target is not None else None,
        "target_exists": target is not None,
        "confidence": entry.confidence,
        "source_updated_at": entry.updated_at,
    }


def _symbolic_node_record(entry: MemoryEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "kind": "Memory",
        "type": entry.type,
        "label": entry.title,
        "payload": {
            "body": entry.body,
            "tags": entry.tags,
            "review_state": entry.review_state,
            "confidence": entry.confidence,
            "privacy": entry.privacy,
            "observed_at": entry.observed_at,
            "valid_from": entry.valid_from,
            "valid_until": entry.valid_until,
        },
        "source_refs": entry.source_refs,
    }


def _symbolic_edge_record(relation: dict[str, object]) -> dict[str, object]:
    source_id = _expect_str(relation, "source_id")
    target_id = _expect_str(relation, "target_id")
    relation_name = _expect_str(relation, "relation")
    return {
        "id": f"{source_id}:{relation_name}:{target_id}",
        "relation": relation_name,
        "source": source_id,
        "target": target_id,
        "payload": {
            "inverse_relation": _optional_str(relation, "inverse_relation"),
            "symmetric": _optional_bool(relation, "symmetric"),
            "transitive": _optional_bool(relation, "transitive"),
            "temporal_policy": _optional_str(relation, "temporal_policy") or "inherits_source",
            "confidence_policy": _optional_str(relation, "confidence_policy") or "inherits_source",
            "retrieval_rule": _optional_str(relation, "retrieval_rule") or "include_direct_neighbors",
            "target_exists": _optional_bool(relation, "target_exists"),
        },
        "confidence": _expect_float(relation, "confidence"),
        "source_refs": [source_id, target_id],
    }


def _relation_record_from_wire(data: dict[str, object]) -> MemoryRelationIndexRecord:
    return MemoryRelationIndexRecord(
        source_id=_expect_str(data, "source_id"),
        target_id=_expect_str(data, "target_id"),
        relation=_expect_str(data, "relation"),
        inverse_relation=_optional_str(data, "inverse_relation"),
        symmetric=_optional_bool(data, "symmetric"),
        transitive=_optional_bool(data, "transitive"),
        temporal_policy=_optional_str(data, "temporal_policy") or "inherits_source",
        confidence_policy=_optional_str(data, "confidence_policy") or "inherits_source",
        retrieval_rule=_optional_str(data, "retrieval_rule") or "include_direct_neighbors",
        source_type=_expect_str(data, "source_type"),
        target_type=_optional_str(data, "target_type"),
        source_title=_expect_str(data, "source_title"),
        target_title=_optional_str(data, "target_title"),
        target_exists=_expect_bool(data, "target_exists"),
        confidence=_expect_float(data, "confidence"),
        source_updated_at=_expect_str(data, "source_updated_at"),
    )


def _matches_relation_filters(
    record: MemoryRelationIndexRecord,
    filters: MemoryRelationFilters | None,
) -> bool:
    if filters is None:
        return True
    if filters.relation is not None and record.relation != filters.relation:
        return False
    if filters.source_id is not None and record.source_id != filters.source_id:
        return False
    if filters.target_id is not None and record.target_id != filters.target_id:
        return False
    return True


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _expect_bool(data: dict[str, object], field_name: str) -> bool:
    value = data.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a boolean")
    return value


def _optional_bool(data: dict[str, object], field_name: str) -> bool:
    value = data.get(field_name)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a boolean or null")
    return value


def _expect_float(data: dict[str, object], field_name: str) -> float:
    value = data.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number")


def _counts(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result
