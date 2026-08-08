"""External source command family."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi, resolve_handle
from nuself.source.record import PrivacyLevel, SourceChunk
from nuself.source.repository import (
    SourceDocumentNotFound,
)
from nuself.source.service import SourceMatch, SourceService
from nuself.cli.handlers import CliHandlerBindings
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


def _format_chunk_match(match: SourceMatch) -> str:
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
    service: SourceService,
) -> str | None:
    return resolve_handle(
        args.source_id,
        service.list(),
        label="source",
        get_id=lambda document: document.id,
    )


def handle_source_ingest(
    args: argparse.Namespace,
) -> int:
    try:
        result = cli_application().source_importer.ingest(
            args.path,
            tags=list(args.tag),
            privacy=_privacy_arg(args.privacy),
        )
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    print(f"Source ingest: {result.summary()}")
    return 0


def handle_source_list(args: argparse.Namespace) -> int:
    documents = cli_application().sources.list()
    if not documents:
        print("No source documents.")
        return 0
    for index, document in enumerate(documents):
        print_ansi(render_source_row(document, index=index))
    return 0


def handle_source_show(args: argparse.Namespace) -> int:
    service = cli_application().sources
    source_id = _resolve_source_id(args, service)
    if source_id is None:
        return 1
    try:
        document = service.get(source_id)
    except SourceDocumentNotFound:
        print(
            f"Source document not found: {source_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(
        render_source_detail(
            document,
            chunk_count=len(service.chunks(document.id)),
        )
    )
    return 0


def handle_source_chunks(
    args: argparse.Namespace,
) -> int:
    service = cli_application().sources
    source_ref = getattr(args, "source_id", None)
    source_id = (
        _resolve_source_id(args, service)
        if source_ref is not None
        else None
    )
    if source_ref is not None and source_id is None:
        return 1
    chunks = service.chunks(source_id)
    if not chunks:
        print("No source chunks.")
        return 0
    for chunk in chunks:
        print(_format_chunk_summary(chunk))
    return 0


def handle_source_search(
    args: argparse.Namespace,
) -> int:
    matches = cli_application().sources.search(
        args.query, limit=args.limit
    )
    if not matches:
        print("No matching source chunks.")
        return 0
    for match in matches:
        print(_format_chunk_match(match))
    return 0


def add_source_parser(subparsers: Any, bindings: CliHandlerBindings) -> None:
    bind = bindings.bind
    source = subparsers.add_parser("source", help="Manage imported external knowledge.")
    bindings.bind_help(source)
    commands = source.add_subparsers(dest="source_command", metavar="<command>")
    ingest = commands.add_parser("ingest", help="Ingest a local document or directory.")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--tag", action="append", default=[])
    ingest.add_argument("--privacy", choices=["private", "shareable"], default="private")
    bind(ingest, handle_source_ingest)
    bind(commands.add_parser("list", help="List source documents."), handle_source_list)
    show = commands.add_parser("show", help="Show a source document.")
    show.add_argument("source_id")
    bind(show, handle_source_show)
    chunks = commands.add_parser("chunks", help="List source chunks.")
    chunks.add_argument("source_id", nargs="?")
    bind(chunks, handle_source_chunks)
    search = commands.add_parser("search", help="Search source chunks.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)
    bind(search, handle_source_search)
