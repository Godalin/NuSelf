"""One-shot thread management command handlers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from nuself.agent.chat import ThreadState, ThreadStore


def handle_thread_list(args: argparse.Namespace) -> int:
    ids = ThreadStore(args.project_root).list()
    if not ids:
        print("No active threads.")
        return 0
    for thread_id in ids:
        print(thread_id)
    return 0


def handle_thread_show(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    state = store.load(args.thread_id)
    if not state.messages and args.thread_id not in store.list():
        print(f"Thread not found: {args.thread_id}", file=sys.stderr)
        return 1
    print(f"Thread: {args.thread_id}")
    if state.summary:
        print(f"Summary: {state.summary}")
    print(f"Messages: {len(state.messages)}")
    for message in state.messages:
        prefix = ">" if message.role == "user" else "<"
        content = message.content[:120]
        if len(message.content) > 120:
            content += "..."
        print(f"  {prefix} {content}")
    return 0


def handle_thread_create(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    if args.thread_id in store.list():
        print(f"Thread already exists: {args.thread_id}", file=sys.stderr)
        return 1
    store.save(ThreadState.empty(args.thread_id))
    print(f"Created thread: {args.thread_id}")
    return 0


def _run_thread_action(
    action: Callable[[], object],
    success: str,
) -> int:
    try:
        action()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(success)
    return 0


def handle_thread_rename(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    return _run_thread_action(
        lambda: store.rename(args.old_thread_id, args.new_thread_id),
        f"Renamed thread: {args.old_thread_id} -> {args.new_thread_id}",
    )


def handle_thread_branch(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    return _run_thread_action(
        lambda: store.branch(
            args.source_thread_id, args.new_thread_id, args.index
        ),
        f"Branched thread: {args.source_thread_id} -> {args.new_thread_id}",
    )


def handle_thread_archive(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    return _run_thread_action(
        lambda: store.archive(args.thread_id),
        f"Archived thread: {args.thread_id}",
    )


def handle_thread_delete(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    return _run_thread_action(
        lambda: store.delete(args.thread_id),
        f"Deleted thread: {args.thread_id}",
    )


def handle_thread_unarchive(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    return _run_thread_action(
        lambda: store.unarchive(args.thread_id),
        f"Unarchived thread: {args.thread_id}",
    )


def handle_thread_archived(args: argparse.Namespace) -> int:
    ids = ThreadStore(args.project_root).list_archived()
    if not ids:
        print("No archived threads.")
        return 0
    for thread_id in ids:
        print(thread_id)
    return 0
