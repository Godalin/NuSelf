"""File-backed repository for user-visible memory entries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
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
    merge_relations,
    now_iso,
)
from nuself.domain.profile import ProfileItem
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import StorageBackend, auto_backend


def empty_str_counts() -> dict[str, int]:
    return {}


def empty_str_floats() -> dict[str, float]:
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
    min_importance: float | None = None


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
    avg_importance: float = 0.0
    max_importance: float = 0.0
    avg_importance_by_type: dict[str, float] = field(default_factory=empty_str_floats)


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


@dataclass(frozen=True)
class SymbolicGraphNode:
    """One derived symbolic graph node."""

    id: str
    kind: str
    type: str
    label: str
    body: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SymbolicGraphEdge:
    """One derived symbolic graph edge."""

    id: str
    relation: str
    source: str
    target: str
    confidence: float


@dataclass(frozen=True)
class SymbolicGraphNodeFilters:
    """Deterministic filters for graph nodes."""

    type: str | None = None


@dataclass(frozen=True)
class SymbolicGraphEdgeFilters:
    """Deterministic filters for graph edges."""

    relation: str | None = None
    source_id: str | None = None
    target_id: str | None = None


@dataclass(frozen=True)
class SymbolicGraphSearchResult:
    """Text-matched graph nodes plus edges up to the requested traversal depth."""

    nodes: tuple[SymbolicGraphNode, ...]
    edges: tuple[SymbolicGraphEdge, ...]


GraphAdjacency = dict[str, list[tuple[str, SymbolicGraphEdge]]]


class MemoryEntryNotFound(KeyError):
    """Raised when a memory entry does not exist."""


class MemoryCandidateNotFound(KeyError):
    """Raised when a memory candidate does not exist."""


def _entry_from_wire(data: dict[str, object]) -> MemoryEntry:
    if "metadata" in data:
        return MemoryEntry.from_memory_object(MemoryObject.from_wire(data))
    return MemoryEntry.from_wire(data)


class MemoryEntryRepository:
    """Stores one JSON file per memory entry under private/memory/entries."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
        registry: MemoryTypeRegistry | None = None,
        relation_registry: RelationDescriptorRegistry | None = None,
    ) -> None:
        be = backend if backend is not None else auto_backend(project_root)
        self._col = be.collection("memory_entries")
        self._paths = runtime_paths(project_root)
        self._registry = registry or default_memory_type_registry()
        self._relation_registry = relation_registry or default_relation_descriptor_registry()

    @property
    def relation_registry(self) -> RelationDescriptorRegistry:
        return self._relation_registry

    def list(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for wire in self._col.list():
            try:
                entries.append(_entry_from_wire(wire))
            except (ValueError, KeyError):
                pass
        return sorted(entries, key=lambda entry: entry.updated_at, reverse=True)

    def search(self, query: str, filters: MemorySearchFilters | None = None) -> list[MemoryEntry]:
        normalized = query.casefold()
        return [
            entry
            for entry in self.list()
            if _matches_text(entry, normalized) and _matches_filters(entry, filters)
        ]

    def get(self, entry_id: str) -> MemoryEntry:
        wire = self._col.get(entry_id)
        if wire is None:
            raise MemoryEntryNotFound(entry_id)
        return _entry_from_wire(wire)

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        if self._registry.get(entry.type) is None and entry.review_state == "draft":
            entry = entry.with_updates(review_state="quarantined")
        else:
            self._registry.validate(entry.to_memory_object())
        self._col.put(entry.id, entry.to_wire())
        return entry

    def unquarantine(self, entry_id: str) -> MemoryEntry:
        entry = self.get(entry_id)
        if entry.review_state != "quarantined":
            raise ValueError(f"entry is not quarantined: {entry_id}")
        updated = entry.with_updates(review_state="draft")
        self._col.put(updated.id, updated.to_wire())
        return updated

    def save_object(self, memory: MemoryObject) -> MemoryObject:
        self._registry.validate(memory)
        self.save(MemoryEntry.from_memory_object(memory))
        return memory

    def delete(self, entry_id: str) -> None:
        wire = self._col.get(entry_id)
        if wire is None:
            raise MemoryEntryNotFound(entry_id)
        self._col.delete(entry_id)

    def reindex(self) -> Path:
        return Path("_reindexed_")

    def reindex_relations(self) -> Path:
        return Path("_reindexed_")

    def reindex_symbolic_graph(self) -> Path:
        return Path("_reindexed_")

    def _compute_relations(self) -> list[MemoryRelationIndexRecord]:
        entries = self.list()
        by_id = {e.id: e for e in entries}
        return [
            _relation_record_from_wire(r)
            for e in entries
            for r in _relation_index_records(e, by_id, self._relation_registry)
        ]

    def list_relations(self, filters: MemoryRelationFilters | None = None) -> list[MemoryRelationIndexRecord]:
        return [r for r in self._compute_relations() if _matches_relation_filters(r, filters)]

    def _compute_graph(self) -> tuple[list[SymbolicGraphNode], list[SymbolicGraphEdge]]:
        entries = self.list()
        by_id = {e.id: e for e in entries}
        nodes = [_symbolic_node_from_wire(_symbolic_node_record(e)) for e in entries]
        edges = [
            _symbolic_edge_from_wire(_symbolic_edge_record(r))
            for e in entries
            for r in _relation_index_records(e, by_id, self._relation_registry)
        ]
        return nodes, edges

    def compute_graph(self) -> tuple[list[SymbolicGraphNode], list[SymbolicGraphEdge]]:
        """Public one-shot graph projection, so callers that need several closures
        (e.g. retrieval expansion) can compute the graph once and reuse it instead
        of rebuilding it from ``list()`` per closure."""
        return self._compute_graph()

    def list_graph_nodes(self, filters: SymbolicGraphNodeFilters | None = None) -> list[SymbolicGraphNode]:
        nodes, _ = self._compute_graph()
        return [n for n in nodes if _matches_graph_node_filters(n, filters)]

    def list_graph_edges(self, filters: SymbolicGraphEdgeFilters | None = None) -> list[SymbolicGraphEdge]:
        _, edges = self._compute_graph()
        return [e for e in edges if _matches_graph_edge_filters(e, filters)]

    def search_graph(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 8,
        depth: int = 1,
    ) -> SymbolicGraphSearchResult:
        nodes, edges = self._compute_graph()
        matched_nodes = [
            node
            for node in nodes
            if _matches_graph_node_filters(node, SymbolicGraphNodeFilters(type=node_type))
            and _matches_graph_text(node, query)
        ][:limit]
        if depth <= 0:
            return SymbolicGraphSearchResult(nodes=tuple(matched_nodes), edges=())

        adjacency = _build_graph_adjacency(edges, self._relation_registry, bidirectional=True)

        frontier = {node.id for node in matched_nodes}
        visited = set(frontier)
        result_node_ids = set(frontier)
        result_edges: list[SymbolicGraphEdge] = []
        seen_edge_ids: set[str] = set()

        for _ in range(depth):
            next_frontier: set[str] = set()
            for node_id in frontier:
                for neighbor_id, edge in adjacency.get(node_id, []):
                    if neighbor_id not in visited:
                        next_frontier.add(neighbor_id)
                        visited.add(neighbor_id)
                        result_node_ids.add(neighbor_id)
                    if edge.id not in seen_edge_ids:
                        seen_edge_ids.add(edge.id)
                        result_edges.append(edge)
            frontier = next_frontier

        node_by_id = {node.id: node for node in nodes}
        matched_ids = {node.id for node in matched_nodes}
        expanded_ids = sorted(result_node_ids - matched_ids)
        result_nodes = tuple(matched_nodes) + tuple(node_by_id[node_id] for node_id in expanded_ids if node_id in node_by_id)
        return SymbolicGraphSearchResult(nodes=result_nodes, edges=tuple(result_edges))

    def find_path(self, from_id: str, to_id: str) -> list[SymbolicGraphEdge]:
        """Return the shortest path from from_id to to_id as a list of edges."""
        _, edges = self._compute_graph()

        adjacency = _build_graph_adjacency(edges, self._relation_registry, bidirectional=True)

        if from_id not in adjacency:
            return []

        queue: list[tuple[str, list[SymbolicGraphEdge]]] = [(from_id, [])]
        visited: set[str] = {from_id}

        while queue:
            current_id, path = queue.pop(0)
            if current_id == to_id:
                return path
            for neighbor_id, edge in adjacency.get(current_id, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [edge]))
        return []

    def transitive_closure(
        self, node_id: str, relation: str
    ) -> SymbolicGraphSearchResult:
        """Return all nodes and edges reachable from node_id via the given relation."""
        return self.transitive_closure_from(self._compute_graph(), node_id, relation)

    def transitive_closure_from(
        self,
        graph: tuple[list[SymbolicGraphNode], list[SymbolicGraphEdge]],
        node_id: str,
        relation: str,
    ) -> SymbolicGraphSearchResult:
        """Compute a transitive closure over an already-computed graph, so a caller
        expanding many nodes reuses one graph instead of rebuilding it per call."""
        nodes, edges = graph

        adjacency = _build_graph_adjacency(
            edges,
            self._relation_registry,
            relation=relation,
            bidirectional=False,
        )

        frontier = {node_id}
        visited = set(frontier)
        result_node_ids = set(frontier)
        result_edges: list[SymbolicGraphEdge] = []
        seen_edge_ids: set[str] = set()

        while frontier:
            next_frontier: set[str] = set()
            for current_id in frontier:
                for neighbor_id, edge in adjacency.get(current_id, []):
                    if neighbor_id not in visited:
                        next_frontier.add(neighbor_id)
                        visited.add(neighbor_id)
                        result_node_ids.add(neighbor_id)
                    if edge.id not in seen_edge_ids:
                        seen_edge_ids.add(edge.id)
                        result_edges.append(edge)
            frontier = next_frontier

        node_by_id = {node.id: node for node in nodes}
        result_nodes = tuple(node_by_id[node_id] for node_id in sorted(result_node_ids) if node_id in node_by_id)
        return SymbolicGraphSearchResult(nodes=result_nodes, edges=tuple(result_edges))


class MemoryCandidateRepository:
    """Stores reviewable memory candidates under private/memory/candidates."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
        entry_repository: MemoryEntryRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
    ) -> None:
        be = backend if backend is not None else auto_backend(project_root)
        self._col = be.collection("memory_candidates")
        self._entry_repository = entry_repository or MemoryEntryRepository(project_root)
        self._profile_repository = profile_repository or ProfileItemRepository(project_root)

    def list(self, *, include_reviewed: bool = False) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        for wire in self._col.list():
            try:
                candidate = MemoryCandidate.from_wire(wire)
            except (ValueError, KeyError):
                continue
            if include_reviewed or candidate.review_state == "pending":
                candidates.append(candidate)
        return sorted(candidates, key=lambda c: c.updated_at, reverse=True)

    def get(self, candidate_id: str) -> MemoryCandidate:
        wire = self._col.get(candidate_id)
        if wire is None:
            raise MemoryCandidateNotFound(candidate_id)
        return MemoryCandidate.from_wire(wire)

    def save(self, candidate: MemoryCandidate) -> MemoryCandidate:
        self._col.put(candidate.id, candidate.to_wire())
        return candidate

    def delete(self, candidate_id: str) -> None:
        wire = self._col.get(candidate_id)
        if wire is None:
            raise MemoryCandidateNotFound(candidate_id)
        self._col.delete(candidate_id)

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
        candidate = self.get(candidate_id)
        updated = candidate.with_updates(
            title=title,
            body=body,
            tags=tags,
            importance=importance,
            observed_at=observed_at,
            valid_from=valid_from,
            valid_until=valid_until,
            temporal_note=temporal_note,
        )
        self.save(updated)
        return updated

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
            return item
        entry = self._entry_repository.save(candidate.to_entry())
        return entry

    def _merge_target(self, candidate: MemoryCandidate, entry_id: str) -> MemoryEntry | ProfileItem:
        if candidate.type == "profile_fact":
            merged = self._profile_repository.merge(candidate, entry_id)
            return merged
        existing = self._entry_repository.get(entry_id)
        merged = MemoryEntry(
            type=existing.type,
            title=candidate.title,
            body=candidate.body,
            tags=candidate.tags or existing.tags,
            source_refs=[*existing.source_refs, *candidate.source_refs],
            confidence=candidate.confidence,
            importance=candidate.importance,
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
            relations=merge_relations(existing.relations, candidate.relations),
            evidence=[*existing.evidence, *candidate.evidence],
        )
        self._entry_repository.save(merged)
        return merged

    def _delete_target(self, candidate: MemoryCandidate) -> MemoryEntry | ProfileItem:
        if candidate.type == "profile_fact":
            item = self._profile_repository.get(candidate.target_entry_id or "")
            self._profile_repository.delete(item.id)
            return item
        entry = self._entry_repository.get(candidate.target_entry_id or "")
        self._entry_repository.delete(candidate.target_entry_id or "")
        return entry


def memory_stats(project_root: Path | None = None) -> MemoryStats:
    """Return compact stats across durable entries and review candidates."""

    entries = MemoryEntryRepository(project_root).list()
    candidates = MemoryCandidateRepository(project_root).list(include_reviewed=True)
    importances = [entry.importance for entry in entries]
    by_type: dict[str, list[float]] = {}
    for entry in entries:
        by_type.setdefault(entry.type, []).append(entry.importance)
    return MemoryStats(
        entries_total=len(entries),
        candidates_total=len(candidates),
        entries_by_type=_counts(entry.type for entry in entries),
        entries_by_review_state=_counts(entry.review_state for entry in entries),
        candidates_by_review_state=_counts(candidate.review_state for candidate in candidates),
        entries_with_observed_at=sum(1 for entry in entries if entry.observed_at is not None),
        entries_with_evidence=sum(1 for entry in entries if entry.evidence),
        pending_candidates=sum(1 for candidate in candidates if candidate.review_state == "pending"),
        avg_importance=sum(importances) / len(importances) if importances else 0.0,
        max_importance=max(importances) if importances else 0.0,
        avg_importance_by_type={t: sum(v) / len(v) for t, v in by_type.items()},
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
    if filters.min_importance is not None and entry.importance < filters.min_importance:
        return False
    return True


def _relation_index_records(
    entry: MemoryEntry,
    by_id: dict[str, MemoryEntry],
    registry: RelationDescriptorRegistry,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for descriptor in registry:
        for target_id in entry.relations.get(descriptor.source_field, []):
            records.append(_relation_index_record(entry, target_id, descriptor, by_id))
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


def _symbolic_node_from_wire(data: dict[str, object]) -> SymbolicGraphNode:
    payload = _expect_dict(data, "payload")
    return SymbolicGraphNode(
        id=_expect_str(data, "id"),
        kind=_expect_str(data, "kind"),
        type=_expect_str(data, "type"),
        label=_expect_str(data, "label"),
        body=_optional_str(payload, "body") or "",
        tags=tuple(_optional_str_list(payload, "tags")),
    )


def _symbolic_edge_from_wire(data: dict[str, object]) -> SymbolicGraphEdge:
    return SymbolicGraphEdge(
        id=_expect_str(data, "id"),
        relation=_expect_str(data, "relation"),
        source=_expect_str(data, "source"),
        target=_expect_str(data, "target"),
        confidence=_expect_float(data, "confidence"),
    )


def _matches_graph_node_filters(
    node: SymbolicGraphNode,
    filters: SymbolicGraphNodeFilters | None,
) -> bool:
    if filters is None:
        return True
    if filters.type is not None and node.type != filters.type:
        return False
    return True


def _matches_graph_text(node: SymbolicGraphNode, query: str) -> bool:
    normalized = query.casefold().strip()
    if normalized == "":
        return True
    return (
        normalized in node.label.casefold()
        or normalized in node.body.casefold()
        or any(normalized in tag.casefold() for tag in node.tags)
    )


def _build_graph_adjacency(
    edges: Iterable[SymbolicGraphEdge],
    relation_registry: RelationDescriptorRegistry,
    *,
    relation: str | None = None,
    bidirectional: bool,
) -> GraphAdjacency:
    adjacency: GraphAdjacency = {}
    for edge in edges:
        if relation is not None and edge.relation != relation:
            continue
        adjacency.setdefault(edge.source, []).append((edge.target, edge))
        descriptor = relation_registry.get(edge.relation)
        if bidirectional or (descriptor is not None and descriptor.symmetric):
            adjacency.setdefault(edge.target, []).append((edge.source, edge))
    return adjacency


def _matches_graph_edge_filters(
    edge: SymbolicGraphEdge,
    filters: SymbolicGraphEdgeFilters | None,
) -> bool:
    if filters is None:
        return True
    if filters.relation is not None and edge.relation != filters.relation:
        return False
    if filters.source_id is not None and edge.source != filters.source_id:
        return False
    if filters.target_id is not None and edge.target != filters.target_id:
        return False
    return True


def _expect_dict(data: dict[str, object], field_name: str) -> dict[str, object]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object")
    return cast(dict[str, object], value)


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


def _optional_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list or null")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
    return result


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
