"""One-shot long-run reasoning command handlers."""

from __future__ import annotations

import argparse
import json
import sys

from nuself.cli_output import print_ansi
from nuself.reason.repository import ReasonNotFound
from nuself.reason.service import ReasonService
from nuself.tui.reason import render_reason_detail, render_reason_row

REASON_VERBS: dict[str, tuple[str, str]] = {
    "advance": ("Advanced", "advance_thread"),
    "pause": ("Paused", "pause_thread"),
    "resume": ("Resumed", "resume_thread"),
    "resolve": ("Resolved", "resolve_thread"),
    "archive": ("Archived", "archive_thread"),
}


def _print_json(*entities: object) -> None:
    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


def handle_reason_list(args: argparse.Namespace) -> int:
    threads = ReasonService(args.project_root).list_threads(
        status=args.status
    )
    if not threads:
        print("No reason threads.")
        return 0
    if args.as_json:
        _print_json(*(thread.to_wire() for thread in threads))
        return 0
    for index, thread in enumerate(threads):
        print_ansi(render_reason_row(thread, index=index))
    return 0


def handle_reason_show(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
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
        _print_json(payload)
        return 0
    print_ansi(
        render_reason_detail(
            thread, steps, full=bool(getattr(args, "full", False))
        )
    )
    return 0


def handle_reason_start(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
    mandates = tuple(getattr(args, "mandate", None) or [])
    try:
        thread = service.start_thread(
            args.topic, priority=args.priority, mandates=mandates
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Started reasoning thread: {thread.id}")
    print_ansi(render_reason_detail(thread))
    return 0


def handle_reason_thread_action(args: argparse.Namespace) -> int:
    verb, method_name = REASON_VERBS[args.action]
    service = ReasonService(args.project_root)
    if args.action == "advance":
        from nuself.llm import configured_langchain_chat_models
        from nuself.reason.advancer import ReasonAdvancer
        from nuself.workspace import PrivateWorkspaceStore

        advancer = ReasonAdvancer(
            project_root=args.project_root,
            workspace_store=PrivateWorkspaceStore(
                args.project_root, scope="reason"
            ),
            langchain_models=configured_langchain_chat_models(
                args.project_root
            ),
        )
        service = ReasonService(args.project_root, advancer=advancer)
    method = getattr(service, method_name)
    try:
        thread = method(args.thread_id)
    except (ReasonNotFound, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
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
        thread_id = ReasonService(args.project_root).delete_thread(
            args.thread_id
        )
    except (ReasonNotFound, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Deleted reason thread: {thread_id}")
    return 0
