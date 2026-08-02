"""One-shot conversation management command handlers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from nuself.conversation import ConversationState
from nuself.cli.composition import cli_application
from nuself.runtime.diagnostics import diagnostic_exception_message


def handle_conversation_list(args: argparse.Namespace) -> int:
    ids = cli_application().conversations.list()
    if not ids:
        print("No active conversations.")
        return 0
    for conversation_id in ids:
        print(conversation_id)
    return 0


def handle_conversation_show(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    state = store.load(args.conversation_id)
    if not state.messages and args.conversation_id not in store.list():
        print(f"Conversation not found: {args.conversation_id}", file=sys.stderr)
        return 1
    print(f"Conversation: {args.conversation_id}")
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


def handle_conversation_create(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    if args.conversation_id in store.list():
        print(f"Conversation already exists: {args.conversation_id}", file=sys.stderr)
        return 1
    store.save(ConversationState.empty(args.conversation_id))
    print(f"Created conversation: {args.conversation_id}")
    return 0


def _run_conversation_action(
    action: Callable[[], object],
    success: str,
) -> int:
    try:
        action()
    except ValueError as exc:
        print(
            f"Error: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(success)
    return 0


def handle_conversation_rename(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    return _run_conversation_action(
        lambda: store.rename(args.old_conversation_id, args.new_conversation_id),
        f"Renamed conversation: {args.old_conversation_id} -> {args.new_conversation_id}",
    )


def handle_conversation_branch(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    return _run_conversation_action(
        lambda: store.branch(
            args.source_conversation_id, args.new_conversation_id, args.index
        ),
        f"Branched conversation: {args.source_conversation_id} -> {args.new_conversation_id}",
    )


def handle_conversation_archive(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    return _run_conversation_action(
        lambda: store.archive(args.conversation_id),
        f"Archived conversation: {args.conversation_id}",
    )


def handle_conversation_delete(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    return _run_conversation_action(
        lambda: store.delete(args.conversation_id),
        f"Deleted conversation: {args.conversation_id}",
    )


def handle_conversation_unarchive(args: argparse.Namespace) -> int:
    store = cli_application().conversations
    return _run_conversation_action(
        lambda: store.unarchive(args.conversation_id),
        f"Unarchived conversation: {args.conversation_id}",
    )


def handle_conversation_archived(args: argparse.Namespace) -> int:
    ids = cli_application().conversations.list_archived()
    if not ids:
        print("No archived conversations.")
        return 0
    for conversation_id in ids:
        print(conversation_id)
    return 0
