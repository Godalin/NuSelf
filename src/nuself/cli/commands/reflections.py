"""One-shot proactive reflection command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi, print_json_lines
from nuself.reflection.repository import ReflectionEntryNotFound
from nuself.reflection.service import ReflectionService
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.reason import render_reason_detail
from nuself.tui.render import (
    render_reflection_entry_detail,
    render_reflection_entry_summary,
)


def _service(args: argparse.Namespace) -> ReflectionService:
    return cli_application().reflection_service


def handle_reflection_list(args: argparse.Namespace) -> int:
    entries = _service(args).list_entries(
        status=args.status
    )
    if not entries:
        filter_msg = (
            f" with status '{args.status}'" if args.status else ""
        )
        print(f"No reflection entries{filter_msg}.")
        return 0
    if args.as_json:
        print_json_lines(*(entry.to_wire() for entry in entries))
        return 0
    for index, entry in enumerate(entries):
        print_ansi(render_reflection_entry_summary(entry, index=index))
    return 0


def handle_reflection_show(args: argparse.Namespace) -> int:
    try:
        entry = _service(args).show_entry(args.entry_id)
    except (ReflectionEntryNotFound, ValueError) as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    if args.as_json:
        print_json_lines(entry.to_wire())
        return 0
    print_ansi(render_reflection_entry_detail(entry))
    return 0


def _change_status(
    args: argparse.Namespace, *, action: str, past_tense: str
) -> int:
    try:
        entry = getattr(_service(args), action)(args.entry_id)
    except (ReflectionEntryNotFound, ValueError) as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    print(f"{past_tense}: {entry.id}")
    return 0


def handle_reflection_dismiss(args: argparse.Namespace) -> int:
    return _change_status(
        args, action="dismiss_entry", past_tense="Dismissed"
    )


def handle_reflection_archive(args: argparse.Namespace) -> int:
    return _change_status(
        args, action="archive_entry", past_tense="Archived"
    )


def handle_reflection_promote(args: argparse.Namespace) -> int:
    try:
        thread = _service(args).promote_to_reason(args.entry_id)
    except (ReflectionEntryNotFound, ValueError, RuntimeError) as exc:
        print(
            f"Error: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Promoted reflection to reason thread: {thread.id}")
    print_ansi(render_reason_detail(thread))
    return 0


def handle_reflection_organize(args: argparse.Namespace) -> int:
    result = _service(args).organize_pending()
    print(
        "Organized reflections: "
        f"merged_groups={result.merged_groups} "
        f"archived_entries={result.archived_entries}"
    )
    return 0
