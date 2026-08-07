"""One-shot proactive reflection command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.application import cli_application
from nuself.agent.endpoint import configured_langchain_chat_models
from nuself.reflection.composition import compose_reflection_scheduler
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.cli.output import print_ansi, print_json_lines
from nuself.reflection.repository import ReflectionEntryNotFound
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.reason import render_reason_detail
from nuself.tui.render import (
    render_reflection_entry_detail,
    render_reflection_entry_summary,
)


def handle_reflection_list(args: argparse.Namespace) -> int:
    entries = cli_application().reflection.list_entries(
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
        entry = cli_application().reflection.show_entry(args.entry_id)
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
        entry = getattr(cli_application().reflection, action)(args.entry_id)
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
        thread = cli_application().reflection.promote_to_reason(args.entry_id)
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
    result = cli_application().reflection.organize_pending()
    print(
        "Organized reflections: "
        f"merged_groups={result.merged_groups} "
        f"archived_entries={result.archived_entries}"
    )
    return 0


def reflection_scheduler() -> ReflectionScheduler:
    application = cli_application()
    return compose_reflection_scheduler(
        application.paths,
        application.memory,
        application.profiles,
        application.sources,
        application.conversation_history,
        application.reflection,
        application.inbox,
        application.deliveries,
        application.trace.recorder,
        config=application.config.reflection,
        language_preference=application.config.chat.language_preference,
        langchain_models=configured_langchain_chat_models(
            application.paths.authority_root,
            config=application.config,
        ),
    )


def handle_reflection_run(args: argparse.Namespace) -> int:
    del args
    scheduler = reflection_scheduler()
    status = scheduler.schedule_status()
    if status.blocked_by == "state_corrupt":
        print("Reflection cannot run: schedule state is corrupt.", file=sys.stderr)
        return 1
    published = scheduler.reflect(force=True)
    print(
        "Reflection cycle published one entry."
        if published
        else "Reflection cycle completed without a new entry."
    )
    return 0


def handle_reflection_status(args: argparse.Namespace) -> int:
    del args
    status = reflection_scheduler().schedule_status()
    print(f"ready: {str(status.ready).lower()}")
    print(f"blocked_by: {status.blocked_by or '-'}")
    print(f"last_run_at: {status.last_run_at.isoformat() if status.last_run_at else '-'}")
    print(f"daily_count: {status.daily_count}")
    return 1 if status.blocked_by == "state_corrupt" else 0
