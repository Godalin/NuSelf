"""Deterministic memory query and context packing."""

from __future__ import annotations

from dataclasses import dataclass
import re

from nuself.domain.memory import MemoryEntry, ReviewState
from nuself.domain.profile import ProfileItem
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceChunkMatch, SourceRepository
from nuself.profile.repository import ProfileItemRepository

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


@dataclass(frozen=True)
class MemoryMatch:
    """A ranked memory entry with explainable match reasons."""

    entry: MemoryEntry
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PackedMemoryContext:
    """Memory context ready to be inserted into an agent prompt."""

    text: str
    matches: tuple[MemoryMatch, ...]
    profile_matches: tuple["ProfileMatch", ...] = ()
    source_matches: tuple[SourceChunkMatch, ...] = ()


@dataclass(frozen=True)
class ProfileMatch:
    """A ranked derived profile item with explainable match reasons."""

    item: ProfileItem
    score: float
    reasons: tuple[str, ...]


class MemoryQueryService:
    """Query durable memory entries and pack relevant context for prompts."""

    def __init__(
        self,
        repository: MemoryEntryRepository,
        source_repository: SourceRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
    ) -> None:
        self._repository = repository
        self._source_repository = source_repository
        self._profile_repository = profile_repository

    def search(self, query: MemoryQuery) -> list[MemoryMatch]:
        tokens = _query_tokens(query.text)
        if not tokens:
            return []
        eligible_entries = [
            entry
            for entry in self._repository.list()
            if entry.review_state in query.review_states and _matches_query_filters(entry.type, entry.tags, query)
        ]
        matches: list[MemoryMatch] = []
        for entry in eligible_entries:
            match = _score_entry(entry, query.text, tokens)
            if match is not None:
                matches.append(match)
        return _expand_related_matches(matches, eligible_entries, query.limit)

    def search_sources(self, query: MemoryQuery) -> list[SourceChunkMatch]:
        if self._source_repository is None:
            return []
        return self._source_repository.search(query.text, limit=query.limit)

    def search_profiles(self, query: MemoryQuery) -> list[ProfileMatch]:
        if self._profile_repository is None:
            return []
        matches: list[ProfileMatch] = []
        for item in self._profile_repository.list():
            if not _matches_query_filters(item.type, item.tags, query):
                continue
            match = _score_profile_item(item, query.text)
            if match is not None:
                matches.append(match)
        return sorted(matches, key=lambda match: (-match.score, match.item.updated_at, match.item.id))[: query.limit]

    def pack(self, query: MemoryQuery) -> PackedMemoryContext:
        matches = tuple(self.search(query))
        profile_matches = tuple(self.search_profiles(query))
        source_matches = tuple(self.search_sources(query))
        if not matches and not profile_matches and not source_matches:
            return PackedMemoryContext(text="", matches=(), profile_matches=(), source_matches=())
        lines: list[str] = []
        if matches:
            lines.append("Memory entries:")
        for match in matches:
            entry = match.entry
            tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
            reasons = ",".join(match.reasons)
            relations = _relation_context(entry)
            relation_text = f" relations={relations}" if relations else ""
            lines.append(
                f"- {entry.title} "
                f"[id={entry.id} type={entry.type} confidence={entry.confidence:.2f}{tags}{relation_text} match={reasons}]: "
                f"{entry.body}"
            )
        if profile_matches:
            if lines:
                lines.append("")
            lines.append("Profile items:")
        for match in profile_matches:
            item = match.item
            tags = f" tags={','.join(item.tags)}" if item.tags else ""
            sources = f" sources={','.join(item.source_refs)}" if item.source_refs else ""
            reasons = ",".join(match.reasons)
            lines.append(
                f"- {item.title} "
                f"[id={item.id} type={item.type} confidence={item.confidence:.2f}{tags}{sources} match={reasons}]: "
                f"{item.body}"
            )
        if source_matches:
            if lines:
                lines.append("")
            lines.append("Source chunks:")
        for match in source_matches:
            chunk = match.chunk
            document = match.document
            tags = f" tags={','.join(document.tags)}" if document.tags else ""
            reasons = ",".join(match.reasons)
            lines.append(
                f"- {document.title} "
                f"[ref={chunk.source_ref} source_id={document.id} kind={document.kind}{tags} match={reasons}]: "
                f"{chunk.text}"
            )
        return PackedMemoryContext(
            text="\n".join(lines),
            matches=matches,
            profile_matches=profile_matches,
            source_matches=source_matches,
        )


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
    return MemoryMatch(entry=entry, score=score, reasons=tuple(reasons))


def _expand_related_matches(
    matches: list[MemoryMatch],
    eligible_entries: list[MemoryEntry],
    limit: int,
) -> list[MemoryMatch]:
    direct_matches = sorted(matches, key=_memory_match_sort_key)
    if len(direct_matches) >= limit:
        return direct_matches[:limit]

    by_id = {entry.id: entry for entry in eligible_entries}
    direct_ids = {match.entry.id for match in direct_matches}
    related_matches: dict[str, MemoryMatch] = {}

    for match in direct_matches:
        for relation, entry_id in _outgoing_relation_refs(match.entry):
            _add_related_match(related_matches, by_id, direct_ids, match, entry_id, relation)
        for relation, entry in _incoming_relation_refs(match.entry, eligible_entries):
            _add_related_match(related_matches, by_id, direct_ids, match, entry.id, relation)

    related_sorted = sorted(related_matches.values(), key=_memory_match_sort_key)
    return [*direct_matches, *related_sorted][:limit]


def _memory_match_sort_key(match: MemoryMatch) -> tuple[float, str, str]:
    return (-match.score, match.entry.updated_at, match.entry.id)


def _outgoing_relation_refs(entry: MemoryEntry) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    refs.extend(("supersedes", entry_id) for entry_id in entry.supersedes)
    refs.extend(("related", entry_id) for entry_id in entry.related_memory_ids)
    return refs


def _incoming_relation_refs(entry: MemoryEntry, entries: list[MemoryEntry]) -> list[tuple[str, MemoryEntry]]:
    refs: list[tuple[str, MemoryEntry]] = []
    for candidate in entries:
        if candidate.id == entry.id:
            continue
        if entry.id in candidate.supersedes:
            refs.append(("superseded_by", candidate))
        if entry.id in candidate.related_memory_ids:
            refs.append(("related_by", candidate))
    return refs


def _add_related_match(
    related_matches: dict[str, MemoryMatch],
    by_id: dict[str, MemoryEntry],
    direct_ids: set[str],
    source_match: MemoryMatch,
    entry_id: str,
    relation: str,
) -> None:
    if entry_id in direct_ids:
        return
    entry = by_id.get(entry_id)
    if entry is None:
        return
    reason = f"{relation}:{source_match.entry.id}"
    score = max(source_match.score - 0.75, 0.1)
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


def _matches_query_filters(memory_type: str, tags: list[str], query: MemoryQuery) -> bool:
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


def _relation_context(entry: MemoryEntry) -> str:
    parts: list[str] = []
    if entry.supersedes:
        parts.append(f"supersedes:{','.join(entry.supersedes)}")
    if entry.related_memory_ids:
        parts.append(f"related:{','.join(entry.related_memory_ids)}")
    return ";".join(parts)


def _score_profile_item(item: ProfileItem, raw_query: str) -> ProfileMatch | None:
    title = item.title.casefold()
    body = item.body.casefold()
    tags = tuple(tag.casefold() for tag in item.tags)
    source_refs = tuple(source_ref.casefold() for source_ref in item.source_refs)
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
    if query != "" and any(query in source_ref for source_ref in source_refs):
        score += 2.0
        reasons.append("source_ref_phrase")

    type_score = _type_affinity_score(item.type, query, _query_tokens(raw_query))
    if type_score > 0.0:
        score += type_score
        reasons.append("type_descriptor")

    for token in _query_tokens(raw_query):
        if token in title:
            score += 3.0
            _append_once(reasons, "title")
        if any(token in tag for tag in tags):
            score += 2.5
            _append_once(reasons, "tag")
        if token in body:
            score += 1.0
            _append_once(reasons, "body")
        if any(token in source_ref for source_ref in source_refs):
            score += 0.5
            _append_once(reasons, "source_ref")

    if score <= 0.0:
        return None
    confidence = item.confidence
    if confidence > 0:
        score += min(confidence, 1.0) * 0.25
        reasons.append("confidence")
    return ProfileMatch(item=item, score=score, reasons=tuple(reasons))


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
