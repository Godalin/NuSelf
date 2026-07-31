"""One-shot proactive reflection command handlers."""

from __future__ import annotations

import argparse
import json
import sys

from nuself.application.reflection import (
    compose_reflection_repository,
    compose_reflection_service,
)
from nuself.cli.composition import compose_cli_application
from nuself.cli.commands.output import print_ansi, resolve_handle
from nuself.config import runtime_paths
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.repository import (
    ReflectionEntryNotFound,
    ReflectionRepository,
)
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.storage import get_default_backend
from nuself.tui.reason import render_reason_detail
from nuself.tui.render import (
    render_reflection_entry_detail,
    render_reflection_entry_summary,
)


def _print_json(*entities: object) -> None:
    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


def _repository(args: argparse.Namespace) -> ReflectionRepository:
    return compose_reflection_repository(
        runtime_paths(args.project_root),
        get_default_backend(args.project_root),
    )


def _resolve_entry_id(args: argparse.Namespace) -> str | None:
    return resolve_handle(
        args.entry_id,
        _repository(args).list(),
        label="reflection",
        get_id=lambda entry: entry.id,
    )


def handle_reflection_list(args: argparse.Namespace) -> int:
    entries = _repository(args).list(
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
        entry = _repository(args).get(entry_id)
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
    repository = _repository(args)
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
        thread = compose_reflection_service(
            compose_cli_application(args.project_root)
        ).promote_to_reason(entry_id)
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
    result = ReflectionOrganizer(
        args.project_root,
        repository=_repository(args),
    ).organize_pending()
    print(
        "Organized reflections: "
        f"merged_groups={result.merged_groups} "
        f"archived_entries={result.archived_entries}"
    )
    return 0
