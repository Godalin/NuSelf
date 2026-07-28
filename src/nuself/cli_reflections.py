"""One-shot proactive reflection command handlers."""

from __future__ import annotations

import argparse
import json
import sys

from nuself.cli_output import print_ansi, resolve_handle
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.repository import (
    ReflectionEntryNotFound,
    ReflectionRepository,
)
from nuself.reflection.service import ReflectionService
from nuself.tui.reason import render_reason_detail
from nuself.tui.render import (
    render_reflection_entry_detail,
    render_reflection_entry_summary,
)


def _print_json(*entities: object) -> None:
    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


def _resolve_entry_id(args: argparse.Namespace) -> str | None:
    return resolve_handle(
        args.entry_id,
        ReflectionRepository(args.project_root).list(),
        label="reflection",
        get_id=lambda entry: entry.id,
    )


def handle_reflection_list(args: argparse.Namespace) -> int:
    entries = ReflectionRepository(args.project_root).list(
        status=args.status
    )
    if not entries:
        filter_msg = (
            f" with status '{args.status}'" if args.status else ""
        )
        print(f"No reflection entries{filter_msg}.")
        return 0
    if args.as_json:
        _print_json(*(entry.to_wire() for entry in entries))
        return 0
    for index, entry in enumerate(entries):
        print_ansi(render_reflection_entry_summary(entry, index=index))
    return 0


def handle_reflection_show(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = ReflectionRepository(args.project_root).get(entry_id)
    except ReflectionEntryNotFound:
        print(f"Reflection entry not found: {entry_id}", file=sys.stderr)
        return 1
    if args.as_json:
        _print_json(entry.to_wire())
        return 0
    print_ansi(render_reflection_entry_detail(entry))
    return 0


def _change_status(
    args: argparse.Namespace, *, action: str, past_tense: str
) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    repository = ReflectionRepository(args.project_root)
    try:
        getattr(repository, action)(entry_id)
    except ReflectionEntryNotFound:
        print(f"Reflection entry not found: {entry_id}", file=sys.stderr)
        return 1
    print(f"{past_tense}: {entry_id}")
    return 0


def handle_reflection_dismiss(args: argparse.Namespace) -> int:
    return _change_status(
        args, action="dismiss", past_tense="Dismissed"
    )


def handle_reflection_archive(args: argparse.Namespace) -> int:
    return _change_status(
        args, action="archive", past_tense="Archived"
    )


def handle_reflection_promote(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        thread = ReflectionService(
            args.project_root
        ).promote_to_reason(entry_id)
    except (ReflectionEntryNotFound, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Promoted reflection to reason thread: {thread.id}")
    print_ansi(render_reason_detail(thread))
    return 0


def handle_reflection_organize(args: argparse.Namespace) -> int:
    result = ReflectionOrganizer(args.project_root).organize_pending()
    print(
        "Organized reflections: "
        f"merged_groups={result.merged_groups} "
        f"archived_entries={result.archived_entries}"
    )
    return 0
