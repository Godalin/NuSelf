"""File-backed source document and chunk repository."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from nuself.config import runtime_paths
from nuself.domain.memory import MemoryCandidate, MemoryEvidence, PrivacyLevel, now_iso
from nuself.domain.source import SourceChunk, SourceDocument, SourceKind, chunk_id_for, source_id_for_path

SUPPORTED_SOURCE_SUFFIXES = {".md", ".markdown", ".txt"}
DEFAULT_CHUNK_TARGET_CHARS = 1200
DEFAULT_SOURCE_SEARCH_LIMIT = 8
WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


@dataclass(frozen=True)
class SourceIngestResult:
    """Result of one source ingestion request."""

    documents: int
    chunks: int

    def summary(self) -> str:
        return f"documents={self.documents} chunks={self.chunks}"


@dataclass(frozen=True)
class SourceChunkMatch:
    """A ranked source chunk with document metadata and match reasons."""

    chunk: SourceChunk
    document: SourceDocument
    score: float
    reasons: tuple[str, ...]


class SourceRepository:
    """Stores imported source documents and chunks under private/sources."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = runtime_paths(project_root)
        self._sources_dir = self._paths.private_root / "sources"
        self._documents_dir = self._sources_dir / "documents"
        self._chunks_dir = self._sources_dir / "chunks"

    def ensure(self) -> None:
        self._documents_dir.mkdir(parents=True, exist_ok=True)
        self._chunks_dir.mkdir(parents=True, exist_ok=True)

    def ingest_path(self, path: Path, *, tags: list[str] | None = None, privacy: PrivacyLevel = "private") -> SourceIngestResult:
        paths = _source_paths(path)
        documents = 0
        chunks = 0
        for source_path in paths:
            document, document_chunks = load_source_file(source_path, tags=tags or [], privacy=privacy)
            self.save_document(document)
            self.replace_chunks(document.id, document_chunks)
            documents += 1
            chunks += len(document_chunks)
        return SourceIngestResult(documents=documents, chunks=chunks)

    def save_document(self, document: SourceDocument) -> SourceDocument:
        self.ensure()
        path = self._document_path(document.id)
        path.write_text(json.dumps(document.to_wire(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return document

    def get_document(self, source_id: str) -> SourceDocument:
        path = self._document_path(source_id)
        if not path.exists():
            raise SourceDocumentNotFound(source_id)
        return self._read_document(path)

    def replace_chunks(self, source_id: str, chunks: list[SourceChunk]) -> None:
        self.ensure()
        for path in self._chunks_dir.glob(f"{source_id}_chunk_*.json"):
            path.unlink()
        for chunk in chunks:
            self._chunk_path(chunk.id).write_text(
                json.dumps(chunk.to_wire(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def list_documents(self) -> list[SourceDocument]:
        self.ensure()
        documents = [self._read_document(path) for path in sorted(self._documents_dir.glob("*.json"))]
        return sorted(documents, key=lambda document: document.updated_at, reverse=True)

    def list_chunks(self, source_id: str | None = None) -> list[SourceChunk]:
        self.ensure()
        pattern = f"{source_id}_chunk_*.json" if source_id is not None else "*.json"
        chunks = [self._read_chunk(path) for path in sorted(self._chunks_dir.glob(pattern))]
        return sorted(chunks, key=lambda chunk: (chunk.source_id, chunk.index))

    def search(self, query: str, *, limit: int = DEFAULT_SOURCE_SEARCH_LIMIT) -> list[SourceChunkMatch]:
        tokens = _query_tokens(query)
        if not tokens:
            return []
        documents = {document.id: document for document in self.list_documents()}
        matches: list[SourceChunkMatch] = []
        for chunk in self.list_chunks():
            document = documents.get(chunk.source_id)
            if document is None:
                continue
            match = _score_chunk(chunk, document, query, tokens)
            if match is not None:
                matches.append(match)
        normalized_limit = max(limit, 1)
        return sorted(matches, key=lambda match: (-match.score, match.chunk.source_ref))[:normalized_limit]

    def reindex(self) -> Path:
        derived_dir = self._paths.private_root / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        documents = {document.id: document for document in self.list_documents()}
        index: list[dict[str, object]] = []
        for chunk in self.list_chunks():
            document = documents.get(chunk.source_id)
            if document is None:
                continue
            index.append(
                {
                    "id": chunk.id,
                    "source_id": chunk.source_id,
                    "source_ref": chunk.source_ref,
                    "index": chunk.index,
                    "title": chunk.title,
                    "path": chunk.path,
                    "document_kind": document.kind,
                    "document_origin": document.origin,
                    "document_privacy": document.privacy,
                    "document_tags": document.tags,
                    "document_source_date": document.source_date,
                    "text": chunk.text,
                    "created_at": chunk.created_at,
                }
            )
        index_path = derived_dir / "source_index.json"
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return index_path

    def extract_candidates(self, source_id: str) -> list[MemoryCandidate]:
        document = self.get_document(source_id)
        chunks = self.list_chunks(source_id)
        return [self._candidate_for_chunk(document, chunk) for chunk in chunks]

    def _document_path(self, source_id: str) -> Path:
        return self._documents_dir / f"{source_id}.json"

    def _chunk_path(self, chunk_id: str) -> Path:
        return self._chunks_dir / f"{chunk_id}.json"

    def _read_document(self, path: Path) -> SourceDocument:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"source document file must contain an object: {path}")
        return SourceDocument.from_wire(cast(dict[str, object], raw))

    def _read_chunk(self, path: Path) -> SourceChunk:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"source chunk file must contain an object: {path}")
        return SourceChunk.from_wire(cast(dict[str, object], raw))

    def _candidate_for_chunk(self, document: SourceDocument, chunk: SourceChunk) -> MemoryCandidate:
        source_ref = chunk.source_ref
        title = f"{document.title} [{chunk.index + 1}]"
        summary = f"Imported from {document.title} chunk {chunk.index + 1}"
        return MemoryCandidate(
            id=f"cand_{uuid5(NAMESPACE_URL, source_ref).hex}",
            action="create",
            type="profile_fact",
            title=title,
            body=chunk.text,
            tags=[*document.tags],
            source_refs=[source_ref],
            confidence=0.75,
            privacy=document.privacy,
            reason=summary,
            observed_at=document.source_date,
            valid_from=document.source_date,
            evidence=[
                MemoryEvidence(
                    source_type="source",
                    source_ref=source_ref,
                    summary=summary,
                    quote=_compact_text(chunk.text, 240),
                    observed_at=document.source_date,
                )
            ],
            temporal_note="Derived from imported source chunk",
        )


def load_source_file(path: Path, *, tags: list[str] | None = None, privacy: PrivacyLevel = "private") -> tuple[SourceDocument, list[SourceChunk]]:
    source_path = path.resolve()
    text = source_path.read_text(encoding="utf-8")
    kind = _source_kind(source_path)
    metadata, body = _parse_metadata(text, source_path, kind)
    merged_tags = [*metadata.tags, *(tags or [])]
    source_id = source_id_for_path(source_path)
    title = metadata.title or _title_from_body(body) or source_path.stem
    document = SourceDocument(
        id=source_id,
        title=title,
        path=str(source_path),
        kind=kind,
        origin=metadata.origin,
        privacy=metadata.privacy or privacy,
        tags=_dedupe_strings(merged_tags),
        source_date=metadata.source_date,
        updated_at=now_iso(),
    )
    chunks = _chunk_text(document, body)
    return document, chunks


@dataclass(frozen=True)
class _SourceMetadata:
    title: str
    tags: list[str]
    source_date: str | None
    origin: str
    privacy: PrivacyLevel | None


class SourceDocumentNotFound(KeyError):
    """Raised when a source document does not exist."""


def _source_paths(path: Path) -> list[Path]:
    resolved = path.resolve()
    if resolved.is_file():
        if resolved.suffix.casefold() not in SUPPORTED_SOURCE_SUFFIXES:
            raise ValueError(f"unsupported source file type: {resolved}")
        return [resolved]
    if resolved.is_dir():
        return [
            item
            for item in sorted(resolved.rglob("*"))
            if item.is_file() and item.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        ]
    raise ValueError(f"source path does not exist: {resolved}")


def _source_kind(path: Path) -> SourceKind:
    if path.suffix.casefold() in {".md", ".markdown"}:
        return "markdown"
    return "text"


def _parse_metadata(text: str, path: Path, kind: SourceKind) -> tuple[_SourceMetadata, str]:
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = index + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().casefold()] = value.strip()
    body = "\n".join(lines[body_start:]).strip()
    title = metadata.get("title", "")
    if title == "" and kind == "markdown":
        title = _markdown_title(body)
    return (
        _SourceMetadata(
            title=title,
            tags=_parse_tags(metadata.get("tags", "")),
            source_date=metadata.get("date"),
            origin=metadata.get("origin", "local"),
            privacy=_parse_privacy(metadata.get("privacy")),
        ),
        body,
    )


def _markdown_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _title_from_body(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    return ""


def _parse_tags(raw: str) -> list[str]:
    if raw == "":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip().strip("'\"") for item in raw.split(",") if item.strip().strip("'\"") != ""]


def _parse_privacy(raw: str | None) -> PrivacyLevel | None:
    if raw is None or raw == "":
        return None
    normalized = raw.casefold()
    if normalized not in {"private", "shareable"}:
        raise ValueError(f"unsupported source privacy: {raw}")
    return cast(PrivacyLevel, normalized)


def _chunk_text(document: SourceDocument, body: str) -> list[SourceChunk]:
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > DEFAULT_CHUNK_TARGET_CHARS:
            chunks.append(current)
            current = paragraph
        else:
            current = paragraph if current == "" else f"{current}\n\n{paragraph}"
    if current:
        chunks.append(current)
    if not chunks and body.strip():
        chunks.append(body.strip())
    return [
        SourceChunk(
            id=chunk_id_for(document.id, index),
            source_id=document.id,
            source_ref=f"source:{document.id}:{index}",
            index=index,
            text=chunk,
            title=document.title,
            path=document.path,
        )
        for index, chunk in enumerate(chunks)
    ]


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _score_chunk(
    chunk: SourceChunk,
    document: SourceDocument,
    raw_query: str,
    tokens: tuple[str, ...],
) -> SourceChunkMatch | None:
    query = raw_query.casefold().strip()
    title = chunk.title.casefold()
    text = chunk.text.casefold()
    path = chunk.path.casefold()
    tags = tuple(tag.casefold() for tag in document.tags)
    origin = document.origin.casefold()
    score = 0.0
    reasons: list[str] = []

    if query != "" and query in title:
        score += 5.0
        reasons.append("title_phrase")
    if query != "" and query in text:
        score += 3.0
        reasons.append("text_phrase")
    if query != "" and any(query in tag for tag in tags):
        score += 4.0
        reasons.append("tag_phrase")

    for token in tokens:
        if token in title:
            score += 3.0
            _append_once(reasons, "title")
        if token in text:
            score += 1.0
            _append_once(reasons, "text")
        if any(token in tag for tag in tags):
            score += 2.5
            _append_once(reasons, "tag")
        if token in path:
            score += 0.5
            _append_once(reasons, "path")
        if token in origin:
            score += 0.5
            _append_once(reasons, "origin")

    if score <= 0.0:
        return None
    return SourceChunkMatch(chunk=chunk, document=document, score=score, reasons=tuple(reasons))


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


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."
