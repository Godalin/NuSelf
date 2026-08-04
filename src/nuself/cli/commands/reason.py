"""One-shot long-run reasoning command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.reason.composition import (
    compose_reason_advancer,
)
from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi, print_json_lines
from nuself.cli.reason_watch import watch_reason_steps
from nuself.reason.errors import ReasonError, ReasonNotFound
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.reason import render_reason_detail, render_reason_row

REASON_VERBS: dict[str, tuple[str, str]] = {
    "advance": ("Advanced", "advance_thread"),
    "pause": ("Paused", "pause_thread"),
    "resume": ("Resumed", "resume_thread"),
    "resolve": ("Resolved", "resolve_thread"),
    "archive": ("Archived", "archive_thread"),
}


def handle_reason_list(args: argparse.Namespace) -> int:
    threads = cli_application().reason.service.list_threads(
        status=args.status
    )
    if not threads:
        print("No reason threads.")
        return 0
    if args.as_json:
        print_json_lines(*(thread.to_wire() for thread in threads))
        return 0
    for index, thread in enumerate(threads):
        print_ansi(render_reason_row(thread, index=index))
    return 0


def handle_reason_show(args: argparse.Namespace) -> int:
    service = cli_application().reason.service
    try:
        thread = service.show_thread(args.thread_id)
    except ReasonNotFound:
        print(
            f"Reason thread not found: {args.thread_id}",
            file=sys.stderr,
        )
        return 1
    steps = service.list_steps(thread.id)
    if args.as_json:
        payload = thread.to_wire()
        payload["steps"] = [step.to_wire() for step in steps]
        print_json_lines(payload)
        return 0
    print_ansi(
        render_reason_detail(
            thread, steps, full=bool(getattr(args, "full", False))
        )
    )
    return 0


def handle_reason_start(args: argparse.Namespace) -> int:
    service = cli_application().reason.service
    mandates = tuple(getattr(args, "mandate", None) or [])
    try:
        thread = service.start_thread(
            args.topic, priority=args.priority, mandates=mandates
        )
    except ReasonError as exc:
        print(
            f"Error: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Started reasoning thread: {thread.id}")
    print_ansi(render_reason_detail(thread))
    return 0


def handle_reason_watch(args: argparse.Namespace) -> int:
    """Run the one-shot argparse adapter for the shared watch loop."""
    watch_reason_steps(
        args.project_root,
        interval=getattr(args, "interval", 5),
        thread_ref=getattr(args, "thread_id", None) or None,
    )
    return 0


def handle_reason_thread_action(args: argparse.Namespace) -> int:
    verb, method_name = REASON_VERBS[args.action]
    application = cli_application()
    service = application.reason.service
    advancer = None
    if args.action == "advance":
        advancer = compose_reason_advancer(
            application.paths,
            application.reason.workspace,
            application.personas,
            application.trace.recorder,
            application.config,
        )
    method = getattr(service, method_name)
    try:
        thread = (
            service.advance_thread(args.thread_id, advancer=advancer)
            if args.action == "advance"
            else method(args.thread_id)
        )
    except ReasonError as exc:
        print(
            f"Error: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"{verb} reason thread: {thread.id}")
    print_ansi(
        render_reason_detail(thread, service.list_steps(thread.id))
    )
    return 0


def handle_reason_delete(args: argparse.Namespace) -> int:
    if not bool(getattr(args, "yes", False)):
        print("Use --yes to confirm deletion.", file=sys.stderr)
        return 1
    try:
        thread_id = cli_application().reason.service.delete_thread(
            args.thread_id
        )
    except ReasonError as exc:
        print(
            f"Error: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Deleted reason thread: {thread_id}")
    return 0
