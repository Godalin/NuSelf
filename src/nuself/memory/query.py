"""Deterministic memory query and context packing."""

from __future__ import annotations

from dataclasses import dataclass
import re

from nuself.domain.memory import MemoryEntry, ReviewState
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceChunkMatch, SourceRepository

DEFAULT_MEMORY_LIMIT = 8
WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


@dataclass(frozen=True)
class MemoryQuery:
    """Input to the memory query service."""

    text: str
    limit: int = DEFAULT_MEMORY_LIMIT
    review_states: tuple[ReviewState, ...] = ("draft", "reviewed")


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
    source_matches: tuple[SourceChunkMatch, ...] = ()


class MemoryQueryService:
    """Query durable memory entries and pack relevant context for prompts."""

    def __init__(self, repository: MemoryEntryRepository, source_repository: SourceRepository | None = None) -> None:
        self._repository = repository
        self._source_repository = source_repository

    def search(self, query: MemoryQuery) -> list[MemoryMatch]:
        tokens = _query_tokens(query.text)
        if not tokens:
            return []
        matches: list[MemoryMatch] = []
        for entry in self._repository.list():
            if entry.review_state not in query.review_states:
                continue
            match = _score_entry(entry, query.text, tokens)
            if match is not None:
                matches.append(match)
        return sorted(matches, key=lambda match: (-match.score, match.entry.updated_at, match.entry.id))[: query.limit]

    def search_sources(self, query: MemoryQuery) -> list[SourceChunkMatch]:
        if self._source_repository is None:
            return []
        return self._source_repository.search(query.text, limit=query.limit)

    def pack(self, query: MemoryQuery) -> PackedMemoryContext:
        matches = tuple(self.search(query))
        source_matches = tuple(self.search_sources(query))
        if not matches and not source_matches:
            return PackedMemoryContext(text="", matches=(), source_matches=())
        lines: list[str] = []
        if matches:
            lines.append("Memory entries:")
        for match in matches:
            entry = match.entry
            tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
            reasons = ",".join(match.reasons)
            lines.append(
                f"- {entry.title} "
                f"[id={entry.id} type={entry.type} confidence={entry.confidence:.2f}{tags} match={reasons}]: "
                f"{entry.body}"
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
        return PackedMemoryContext(text="\n".join(lines), matches=matches, source_matches=source_matches)


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
