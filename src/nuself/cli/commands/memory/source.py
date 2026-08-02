"""One-shot memory source command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi, resolve_handle
from nuself.memory.model import PrivacyLevel
from nuself.memory.source_model import SourceChunk
from nuself.memory.source_repository import (
    SourceChunkMatch,
    SourceDocumentNotFound,
    SourceRepository,
)
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.memory import render_source_detail, render_source_row


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _format_chunk_summary(chunk: SourceChunk) -> str:
    preview = _compact_text(chunk.text, 96)
    return (
        f"{chunk.source_ref} {chunk.title} "
        f"chars={len(chunk.text)} {preview}"
    )


def _format_chunk_match(match: SourceChunkMatch) -> str:
    chunk = match.chunk
    document = match.document
    reasons = ",".join(match.reasons)
    tags = ",".join(document.tags) if document.tags else "-"
    return (
        f"{chunk.source_ref} {document.title} "
        f"score={match.score:.2f} match={reasons} "
        f"tags={tags} path={document.path} "
        f"{_compact_text(chunk.text, 96)}"
    )


def _privacy_arg(value: object) -> PrivacyLevel:
    return "shareable" if value == "shareable" else "private"


def _resolve_source_id(
    args: argparse.Namespace,
    repository: SourceRepository,
) -> str | None:
    return resolve_handle(
        args.source_id,
        repository.list_documents(),
        label="source",
        get_id=lambda document: document.id,
    )


def handle_memory_source_ingest(
    args: argparse.Namespace,
) -> int:
    try:
        result = cli_application().memory.sources.ingest_path(
            args.path,
            tags=list(args.tag),
            privacy=_privacy_arg(args.privacy),
        )
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    print(f"Source ingest: {result.summary()}")
    return 0


def handle_memory_source_list(args: argparse.Namespace) -> int:
    documents = cli_application().memory.sources.list_documents()
    if not documents:
        print("No source documents.")
        return 0
    for index, document in enumerate(documents):
        print_ansi(render_source_row(document, index=index))
    return 0


def handle_memory_source_show(args: argparse.Namespace) -> int:
    repository = cli_application().memory.sources
    source_id = _resolve_source_id(args, repository)
    if source_id is None:
        return 1
    try:
        document = repository.get_document(source_id)
    except SourceDocumentNotFound:
        print(
            f"Source document not found: {source_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(
        render_source_detail(
            document,
            chunk_count=len(repository.list_chunks(document.id)),
        )
    )
    return 0


def handle_memory_source_delete(
    args: argparse.Namespace,
) -> int:
    memory = cli_application().memory
    repository = memory.sources
    source_id = _resolve_source_id(args, repository)
    if source_id is None:
        return 1
    try:
        repository.delete_document(source_id)
    except SourceDocumentNotFound:
        print(
            f"Source document not found: {source_id}",
            file=sys.stderr,
        )
        return 1
    print(f"Deleted source document: {source_id}")
    return 0


def handle_memory_source_chunks(
    args: argparse.Namespace,
) -> int:
    repository = cli_application().memory.sources
    source_ref = getattr(args, "source_id", None)
    source_id = (
        _resolve_source_id(args, repository)
        if source_ref is not None
        else None
    )
    if source_ref is not None and source_id is None:
        return 1
    chunks = repository.list_chunks(source_id)
    if not chunks:
        print("No source chunks.")
        return 0
    for chunk in chunks:
        print(_format_chunk_summary(chunk))
    return 0


def handle_memory_source_search(
    args: argparse.Namespace,
) -> int:
    matches = cli_application().memory.sources.search(
        args.query, limit=args.limit
    )
    if not matches:
        print("No matching source chunks.")
        return 0
    for match in matches:
        print(_format_chunk_match(match))
    return 0


def handle_memory_source_extract(
    args: argparse.Namespace,
) -> int:
    memory = cli_application().memory
    source_id = _resolve_source_id(args, memory.sources)
    if source_id is None:
        return 1
    try:
        candidates = memory.sources.extract_candidates(source_id)
    except SourceDocumentNotFound:
        print(
            f"Source document not found: {source_id}",
            file=sys.stderr,
        )
        return 1
    if not candidates:
        print("No source chunks to extract.")
        return 0
    candidate_repository = memory.candidates
    for candidate in candidates:
        candidate_repository.save(candidate)
    print(
        "Extracted source candidates: "
        f"source={source_id} candidates={len(candidates)}"
    )
    return 0
