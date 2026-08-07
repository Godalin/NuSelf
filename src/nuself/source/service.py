"""Public application API for external knowledge sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from nuself.source import local
from nuself.source.record import PrivacyLevel, SourceChunk, SourceDocument
from nuself.source.repository import SourceRepository

DEFAULT_LIMIT = 8
WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


@dataclass(frozen=True)
class SourceIngestResult:
    documents: int
    chunks: int

    def summary(self) -> str:
        return f"documents={self.documents} chunks={self.chunks}"


@dataclass(frozen=True)
class SourceMatch:
    chunk: SourceChunk
    document: SourceDocument
    score: float
    reasons: tuple[str, ...]


class SourceService:
    """Ingest and query external knowledge without Memory side effects."""

    def __init__(self, repository: SourceRepository) -> None:
        self._repository = repository

    def ingest(self, path: Path, *, tags: list[str] | None = None, privacy: PrivacyLevel = "private") -> SourceIngestResult:
        document_count = 0
        chunk_count = 0
        for source_path in local.source_paths(path):
            document, chunks = local.load(source_path, tags=tags, privacy=privacy)
            self._repository.replace(document, chunks)
            document_count += 1
            chunk_count += len(chunks)
        return SourceIngestResult(document_count, chunk_count)

    def get(self, source_id: str) -> SourceDocument:
        return self._repository.get_document(source_id)

    def get_chunk(self, chunk_id: str) -> SourceChunk:
        return self._repository.get_chunk(chunk_id)

    def list(self) -> list[SourceDocument]:
        return self._repository.list_documents()

    def chunks(self, source_id: str | None = None) -> list[SourceChunk]:
        return self._repository.list_chunks(source_id)

    def delete(self, source_id: str) -> None:
        self._repository.delete_document(source_id)

    def search(self, query: str, *, limit: int = DEFAULT_LIMIT) -> list[SourceMatch]:
        tokens = _tokens(query)
        if not tokens:
            return []
        documents = {document.id: document for document in self.list()}
        matches: list[SourceMatch] = []
        for chunk in self.chunks():
            document = documents.get(chunk.source_id)
            if document is None:
                continue
            match = _score(chunk, document, query, tokens)
            if match is not None:
                matches.append(match)
        return sorted(matches, key=lambda item: (-item.score, item.chunk.source_ref))[:max(limit, 1)]


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0) for match in WORD_RE.finditer(text.casefold()) if len(match.group(0)) >= 2))


def _score(chunk: SourceChunk, document: SourceDocument, raw_query: str, tokens: tuple[str, ...]) -> SourceMatch | None:
    query = raw_query.casefold().strip()
    fields = {
        "title": chunk.title.casefold(),
        "text": chunk.text.casefold(),
        "path": chunk.path.casefold(),
        "origin": document.origin.casefold(),
    }
    tags = tuple(tag.casefold() for tag in document.tags)
    score = 0.0
    reasons: list[str] = []
    for name, weight in (("title", 5.0), ("text", 3.0)):
        if query and query in fields[name]:
            score += weight
            reasons.append(f"{name}_phrase")
    if query and any(query in tag for tag in tags):
        score += 4.0
        reasons.append("tag_phrase")
    for token in tokens:
        for name, weight in (("title", 3.0), ("text", 1.0), ("path", 0.5), ("origin", 0.5)):
            if token in fields[name]:
                score += weight
                if name not in reasons:
                    reasons.append(name)
        if any(token in tag for tag in tags):
            score += 2.5
            if "tag" not in reasons:
                reasons.append("tag")
    return SourceMatch(chunk, document, score, tuple(reasons)) if score > 0 else None
