"""Personal long-term memory application service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import re

from nuself.memory.model import MemoryCandidate, MemoryEntry, MemoryTypeRegistry, RelationDescriptor, RelationDescriptorRegistry, ReviewState, default_memory_type_registry
from nuself.profile.model import ProfileItem
from nuself.config.settings import SystemConfig
from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.memory.curator.worker import MemoryCurator
from nuself.memory.curator.plan import MemoryCuratorPlan, MemoryCuratorPlanStore
from nuself.memory.observation import MemoryObservation, MemoryObservationRepository
from nuself.memory.optimizer import MemoryOptimizer, MemoryOptimizerSettings
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
    MemoryRelationFilters,
    MemoryRelationIndexRecord,
    MemorySearchFilters,
    MemoryStats,
    SymbolicGraphEdge,
    SymbolicGraphEdgeFilters,
    SymbolicGraphNode,
    SymbolicGraphNodeFilters,
    SymbolicGraphSearchResult,
    memory_stats,
)

DEFAULT_MEMORY_LIMIT = 8
WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


@dataclass(frozen=True)
class MemoryQuery:
    """Input to the memory query service."""

    text: str
    limit: int = DEFAULT_MEMORY_LIMIT
    review_states: tuple[ReviewState, ...] = ("draft", "reviewed")
    memory_types: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    min_importance: float | None = None


@dataclass(frozen=True)
class MemoryMatch:
    """A ranked memory entry with explainable match reasons."""

    entry: MemoryEntry
    score: float
    reasons: tuple[str, ...]


class MemoryService:
    """Single authority-scoped boundary for all public Memory behavior."""

    def __init__(
        self,
        repository: MemoryEntryRepository,
        candidate_repository: MemoryCandidateRepository | None = None,
        relation_registry: RelationDescriptorRegistry | None = None,
        registry: MemoryTypeRegistry | None = None,
        observation_repository: MemoryObservationRepository | None = None,
        curator_plan_store: MemoryCuratorPlanStore | None = None,
        curator_factory: Callable[
            [SystemConfig, tuple[LangChainLLMEndpoint, ...] | None],
            MemoryCurator,
        ]
        | None = None,
        optimizer_factory: Callable[
            [SystemConfig, MemoryOptimizerSettings | None],
            MemoryOptimizer,
        ]
        | None = None,
    ) -> None:
        self._repository = repository
        self._candidate_repository = candidate_repository
        self._relation_registry = relation_registry or repository.relation_registry
        self._registry = registry or default_memory_type_registry()
        self._observation_repository = observation_repository
        self._curator_plan_store = curator_plan_store
        self._curator_factory = curator_factory
        self._optimizer_factory = optimizer_factory

    def search(self, query: MemoryQuery) -> list[MemoryMatch]:
        tokens = _query_tokens(query.text)
        if not tokens:
            return []
        eligible_entries = [
            entry
            for entry in self._repository.list()
            if entry.review_state in query.review_states
            and _matches_query_filters(entry.type, entry.tags, query)
            and self._registry.retrieve(entry.type, query.text, query.limit)
        ]
        matches: list[MemoryMatch] = []
        for entry in eligible_entries:
            if query.min_importance is not None and entry.importance < query.min_importance:
                continue
            match = _score_entry(entry, query.text, tokens)
            if match is not None:
                matches.append(match)
        return _expand_related_matches(
            matches,
            eligible_entries,
            query.limit,
            self._relation_registry,
            self._repository,
        )

    def list_entries(self) -> list[MemoryEntry]:
        """List inspectable memory entries."""

        return self._repository.list()

    def search_entries(
        self,
        query: str,
        filters: MemorySearchFilters | None = None,
    ) -> list[MemoryEntry]:
        """Search entries using deterministic maintenance filters."""

        eligible_ids = {
            entry.id for entry in self._repository.search("", filters)
        }
        if query.strip() == "":
            return [
                entry
                for entry in self._repository.list()
                if entry.id in eligible_ids
            ]
        matches = self.search(
            MemoryQuery(
                text=query,
                limit=max(len(eligible_ids), 1),
                review_states=(
                    "draft",
                    "reviewed",
                    "rejected",
                    "quarantined",
                    "archived",
                ),
            )
        )
        return [
            match.entry
            for match in matches
            if match.entry.id in eligible_ids
        ]

    def get_entry(self, entry_id: str) -> MemoryEntry:
        """Get one inspectable memory entry."""

        return self._repository.get(entry_id)

    def save_entry(self, entry: MemoryEntry) -> MemoryEntry:
        """Persist a complete validated memory entry."""

        return self._repository.save(entry)

    def delete_entry(self, entry_id: str) -> None:
        """Delete one memory entry."""

        self._repository.delete(entry_id)

    def unquarantine_entry(self, entry_id: str) -> MemoryEntry:
        """Restore one quarantined entry to draft review."""

        return self._repository.unquarantine(entry_id)

    def statistics(self) -> MemoryStats:
        """Summarize memory entry and candidate state."""

        return memory_stats(self._repository, self._candidates())

    def list_candidates(
        self,
        *,
        include_reviewed: bool = False,
    ) -> list[MemoryCandidate]:
        """List candidate memories awaiting or completing review."""

        return self._candidates().list(include_reviewed=include_reviewed)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate:
        """Get one candidate memory."""

        return self._candidates().get(candidate_id)

    def accept_candidate(self, candidate_id: str) -> MemoryEntry | ProfileItem:
        """Promote one candidate into its canonical destination."""

        return self._candidates().accept(candidate_id)

    def reject_candidate(self, candidate_id: str) -> MemoryCandidate:
        """Reject one candidate memory."""

        return self._candidates().reject(candidate_id)

    def edit_candidate(
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
        """Edit a candidate before review."""

        return self._candidates().edit(
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

    def merge_candidate(
        self,
        candidate_id: str,
        entry_id: str,
    ) -> MemoryEntry | ProfileItem:
        """Merge one candidate into an existing memory or profile item."""

        return self._candidates().merge(candidate_id, entry_id)

    def delete_candidate(self, candidate_id: str) -> None:
        """Delete one candidate memory."""

        self._candidates().delete(candidate_id)

    def observe(self, observation: MemoryObservation) -> MemoryObservation:
        """Persist producer-neutral observation input."""
        return self._observations().observe(observation)

    def pending_observations(self) -> tuple[MemoryObservation, ...]:
        """List durable observations awaiting curation."""
        return self._observations().pending()

    def curator_plan(self, observation_id: str) -> MemoryCuratorPlan | None:
        """Read one durable curator recovery plan."""
        return self._plans().get(observation_id)

    def discard_curator_plan(self, observation_id: str) -> None:
        """Discard one completed or abandoned recovery plan."""
        self._plans().discard(observation_id)

    def curator(
        self,
        config: SystemConfig,
        *,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> MemoryCurator:
        """Build one curator over this service's authority graph."""
        if self._curator_factory is None:
            raise RuntimeError("memory curation is unavailable")
        return self._curator_factory(
            config,
            langchain_models,
        )

    def optimizer(
        self,
        config: SystemConfig,
        *,
        settings: MemoryOptimizerSettings | None = None,
    ) -> MemoryOptimizer:
        """Build one optimizer over this service's authority graph."""
        if self._optimizer_factory is None:
            raise RuntimeError("memory optimization is unavailable")
        return self._optimizer_factory(config, settings)

    def _candidates(self) -> MemoryCandidateRepository:
        if self._candidate_repository is None:
            raise RuntimeError("memory candidate operations are unavailable")
        return self._candidate_repository

    def _observations(self) -> MemoryObservationRepository:
        if self._observation_repository is None:
            raise RuntimeError("memory observation intake is unavailable")
        return self._observation_repository

    def _plans(self) -> MemoryCuratorPlanStore:
        if self._curator_plan_store is None:
            raise RuntimeError("memory curator plans are unavailable")
        return self._curator_plan_store

    def list_relations(
        self,
        filters: MemoryRelationFilters | None = None,
    ) -> list[MemoryRelationIndexRecord]:
        """List the current derived relation projection."""

        return self._repository.list_relations(filters)

    def list_graph_nodes(
        self,
        filters: SymbolicGraphNodeFilters | None = None,
    ) -> list[SymbolicGraphNode]:
        """List nodes in the current symbolic projection."""

        return self._repository.list_graph_nodes(filters)

    def list_graph_edges(
        self,
        filters: SymbolicGraphEdgeFilters | None = None,
    ) -> list[SymbolicGraphEdge]:
        """List edges in the current symbolic projection."""

        return self._repository.list_graph_edges(filters)

    def search_graph(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 20,
        depth: int = 1,
    ) -> SymbolicGraphSearchResult:
        """Search the symbolic projection and return bounded context."""

        return self._repository.search_graph(
            query,
            node_type=node_type,
            limit=limit,
            depth=depth,
        )

    def find_graph_path(
        self,
        from_id: str,
        to_id: str,
    ) -> list[SymbolicGraphEdge]:
        """Find one path through the symbolic projection."""

        return self._repository.find_path(from_id, to_id)

    def graph_closure(
        self,
        node_id: str,
        relation: str,
    ) -> SymbolicGraphSearchResult:
        """Return the transitive closure for one registered relation."""

        return self._repository.transitive_closure(node_id, relation)

    def count(
        self,
        *,
        memory_types: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> int:
        """Count entries matching optional type and tag filters."""

        entries = self._repository.list()
        if memory_types:
            entries = [entry for entry in entries if entry.type in memory_types]
        if tags:
            tag_set = set(tags)
            entries = [
                entry for entry in entries if tag_set.intersection(entry.tags)
            ]
        return len(entries)

    def archive(self, entry_id: str) -> MemoryEntry:
        """Archive one entry."""

        entry = self._repository.get(entry_id)
        updated = entry.with_updates(review_state="archived")
        self._repository.save(updated)
        return updated

    def update_importance(
        self,
        entry_id: str,
        *,
        importance: float,
    ) -> MemoryEntry:
        """Update entry importance."""

        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be between 0.0 and 1.0")
        entry = self._repository.get(entry_id)
        updated = entry.with_updates(importance=importance)
        self._repository.save(updated)
        return updated

def _score_entry(entry: MemoryEntry, raw_query: str, tokens: tuple[str, ...]) -> MemoryMatch | None:
    title = entry.title.casefold()
    body = entry.body.casefold()
    tags = tuple(tag.casefold() for tag in entry.tags)
    query = raw_query.casefold().strip()
    score = 0.0
    reasons: list[str] = []

    if query != "" and query in title:
        score += 5.0
        reasons.append("title_phrase")
    if query != "" and query in body:
        score += 3.0
        reasons.append("body_phrase")
    if query != "" and any(query in tag for tag in tags):
        score += 4.0
        reasons.append("tag_phrase")

    type_score = _type_affinity_score(entry.type, query, tokens)
    if type_score > 0.0:
        score += type_score
        reasons.append("type_descriptor")

    for token in tokens:
        if token in title:
            score += 3.0
            _append_once(reasons, "title")
        if any(token in tag for tag in tags):
            score += 2.5
            _append_once(reasons, "tag")
        if token in body:
            score += 1.0
            _append_once(reasons, "body")

    if score <= 0.0:
        return None
    if entry.review_state == "reviewed":
        score += 0.5
        reasons.append("reviewed")
    if entry.confidence > 0:
        score += min(entry.confidence, 1.0) * 0.25
        reasons.append("confidence")
    if entry.importance > 0:
        score += min(entry.importance, 1.0) * 0.5
        reasons.append("importance")
    return MemoryMatch(entry=entry, score=score, reasons=tuple(reasons))


def _expand_related_matches(
    matches: list[MemoryMatch],
    eligible_entries: list[MemoryEntry],
    limit: int,
    registry: RelationDescriptorRegistry,
    repository: MemoryEntryRepository,
) -> list[MemoryMatch]:
    direct_matches = sorted(matches, key=_memory_match_sort_key)
    if len(direct_matches) >= limit:
        return direct_matches[:limit]

    by_id = {entry.id: entry for entry in eligible_entries}
    direct_ids = {match.entry.id for match in direct_matches}
    related_matches: dict[str, MemoryMatch] = {}

    # Project the symbolic graph once for the whole expansion instead of rebuilding
    # it from list() inside transitive_closure per (match, relation).
    graph = repository.compute_graph() if any(descriptor.transitive for descriptor in registry) else None

    for match in direct_matches:
        for descriptor, entry_id in _outgoing_relation_refs(match.entry, registry):
            _add_related_match(related_matches, by_id, direct_ids, match, entry_id, descriptor, descriptor.name)
        for descriptor, entry in _incoming_relation_refs(match.entry, eligible_entries, registry):
            _add_related_match(related_matches, by_id, direct_ids, match, entry.id, descriptor, descriptor.inverse or descriptor.name)
        for descriptor, entry_id in _transitive_relation_refs(match.entry, registry, repository, graph):
            _add_related_match(
                related_matches,
                by_id,
                direct_ids,
                match,
                entry_id,
                descriptor,
                f"{descriptor.name}_closure",
                extra_penalty=0.25,
            )

    related_sorted = sorted(related_matches.values(), key=_memory_match_sort_key)
    return [*direct_matches, *related_sorted][:limit]


def _memory_match_sort_key(match: MemoryMatch) -> tuple[float, str, str]:
    return (-match.score, match.entry.updated_at, match.entry.id)


def _outgoing_relation_refs(
    entry: MemoryEntry, registry: RelationDescriptorRegistry
) -> list[tuple[RelationDescriptor, str]]:
    refs: list[tuple[RelationDescriptor, str]] = []
    for descriptor in registry:
        for target_id in entry.relations.get(descriptor.source_field, []):
            refs.append((descriptor, target_id))
    return refs


def _incoming_relation_refs(
    entry: MemoryEntry, entries: list[MemoryEntry], registry: RelationDescriptorRegistry
) -> list[tuple[RelationDescriptor, MemoryEntry]]:
    refs: list[tuple[RelationDescriptor, MemoryEntry]] = []
    for candidate in entries:
        if candidate.id == entry.id:
            continue
        for descriptor in registry:
            if entry.id in candidate.relations.get(descriptor.source_field, []):
                refs.append((descriptor, candidate))
    return refs


def _transitive_relation_refs(
    entry: MemoryEntry,
    registry: RelationDescriptorRegistry,
    repository: MemoryEntryRepository,
    graph: tuple[list[SymbolicGraphNode], list[SymbolicGraphEdge]] | None = None,
) -> list[tuple[RelationDescriptor, str]]:
    refs: list[tuple[RelationDescriptor, str]] = []
    for descriptor in registry:
        if not descriptor.transitive:
            continue
        direct_targets = set(entry.relations.get(descriptor.source_field, []))
        if graph is None:
            graph = repository.compute_graph()
        closure = repository.transitive_closure_from(graph, entry.id, descriptor.name)
        for node in closure.nodes:
            if node.id != entry.id and node.id not in direct_targets:
                refs.append((descriptor, node.id))
    return refs


def _relation_score_penalty(descriptor: RelationDescriptor) -> float:
    if descriptor.retrieval_rule == "include_both_current_and_superseded":
        return 0.5
    return 0.75


def _add_related_match(
    related_matches: dict[str, MemoryMatch],
    by_id: dict[str, MemoryEntry],
    direct_ids: set[str],
    source_match: MemoryMatch,
    entry_id: str,
    descriptor: RelationDescriptor,
    relation_name: str,
    extra_penalty: float = 0.0,
) -> None:
    if entry_id in direct_ids:
        return
    entry = by_id.get(entry_id)
    if entry is None:
        return
    reason = f"{relation_name}:{source_match.entry.id}"
    score = max(source_match.score - _relation_score_penalty(descriptor) - extra_penalty, 0.1)
    current = related_matches.get(entry.id)
    if current is None:
        related_matches[entry.id] = MemoryMatch(entry=entry, score=score, reasons=(reason,))
        return
    if score > current.score:
        related_matches[entry.id] = MemoryMatch(entry=entry, score=score, reasons=(*current.reasons, reason))
    elif reason not in current.reasons:
        related_matches[entry.id] = MemoryMatch(
            entry=entry,
            score=current.score,
            reasons=(*current.reasons, reason),
        )


def _matches_query_filters(
    memory_type: str,
    tags: Sequence[str],
    query: MemoryQuery,
) -> bool:
    if query.memory_types and memory_type not in query.memory_types:
        return False
    if query.tags:
        normalized_tags = {tag.casefold() for tag in tags}
        if not all(tag.casefold() in normalized_tags for tag in query.tags):
            return False
    return True


TYPE_QUERY_HINTS: dict[str, tuple[str, ...]] = {
    "preference": ("prefer", "preference", "like", "favorite", "choice", "rather"),
    "style_trait": ("style", "tone", "voice", "respond", "answer", "write", "communication"),
    "instruction": ("instruction", "rule", "should", "must", "always", "never", "respond", "behavior"),
    "goal": ("goal", "plan", "next", "current", "focus", "todo", "blocker", "progress"),
    "belief": ("belief", "believe", "think", "opinion", "view", "stance", "claim"),
    "concept": ("concept", "meaning", "definition", "define", "idea", "explain"),
    "episode": ("when", "happened", "discussed", "history", "previously", "earlier", "event"),
    "open_question": ("question", "unknown", "unresolved", "open", "unclear"),
    "profile_fact": ("profile", "about", "background", "fact", "identity"),
    "source_note": ("source", "note", "document", "evidence", "reference"),
}


def _type_affinity_score(memory_type: str, query: str, tokens: tuple[str, ...]) -> float:
    hints = TYPE_QUERY_HINTS.get(memory_type)
    if not hints:
        return 0.0
    score = 0.0
    for hint in hints:
        hint_normalized = hint.casefold()
        if " " in hint_normalized and hint_normalized in query:
            score += 1.5
        elif hint_normalized in tokens:
            score += 1.0
    return min(score, 3.0)
def _query_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for match in WORD_RE.finditer(text.casefold()):
        token = match.group(0)
        if len(token) < 2:
            continue
        if token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def _append_once(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)
