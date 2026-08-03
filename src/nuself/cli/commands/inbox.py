"""Generic Inbox command handlers."""

from __future__ import annotations

import argparse
import select
import sys
import time
from typing import cast

from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi, resolve_handle
from nuself.delivery.composition import build_delivery_adapters
from nuself.delivery.loop import DeliveryLoop
from nuself.inbox.model import InboxClearStatus, InboxStatus
from nuself.inbox.service import InboxItemNotFound, InboxService
from nuself.tui.render import render_inbox_detail, render_inbox_summary


def _resolve(args: argparse.Namespace, inbox: InboxService) -> str | None:
    return resolve_handle(
        args.entry_id, inbox.list(), label="Inbox item", get_id=lambda item: item.id
    )


def handle_inbox(args: argparse.Namespace) -> int:
    """List pending Inbox items."""

    args.status = "pending"
    return handle_inbox_list(args)


def handle_inbox_list(args: argparse.Namespace) -> int:
    status = cast(InboxStatus | None, getattr(args, "status", None))
    items = cli_application().inbox.list(status=status)
    if not items:
        print("Inbox is empty." if status == "pending" else "No Inbox items.")
        return 0
    for index, item in enumerate(items):
        print_ansi(render_inbox_summary(item, index=index))
    return 0


def handle_inbox_show(args: argparse.Namespace) -> int:
    inbox = cli_application().inbox
    item_id = _resolve(args, inbox)
    if item_id is None:
        return 1
    try:
        item = inbox.get(item_id)
    except InboxItemNotFound:
        print(f"Inbox item not found: {item_id}", file=sys.stderr)
        return 1
    if item.status == "pending":
        item = inbox.mark_read(item.id)
    print_ansi(render_inbox_detail(item))
    return 0


def _transition(args: argparse.Namespace, action: str, label: str) -> int:
    inbox = cli_application().inbox
    item_id = _resolve(args, inbox)
    if item_id is None:
        return 1
    try:
        getattr(inbox, action)(item_id)
    except InboxItemNotFound:
        print(f"Inbox item not found: {item_id}", file=sys.stderr)
        return 1
    print(f"{label}: {item_id}")
    return 0


def handle_inbox_read(args: argparse.Namespace) -> int:
    return _transition(args, "mark_read", "Read")


def handle_inbox_dismiss(args: argparse.Namespace) -> int:
    return _transition(args, "dismiss", "Dismissed")


def handle_inbox_resolve(args: argparse.Namespace) -> int:
    return _transition(args, "resolve", "Resolved")


def handle_inbox_send(args: argparse.Namespace) -> int:
    application = cli_application()
    item_id = _resolve(args, application.inbox)
    if item_id is None:
        return 1
    try:
        item = application.inbox.get(item_id)
    except InboxItemNotFound:
        print(f"Inbox item not found: {item_id}", file=sys.stderr)
        return 1
    record = application.deliveries.request(item.id, context=item.context)
    final = DeliveryLoop(
        application.inbox,
        application.deliveries,
        build_delivery_adapters(
            application.paths,
            email_config=application.config.email,
            macos_config=application.config.macos_notification,
        ),
    ).deliver(record.id)
    if final.status == "sent":
        print(f"Sent: {item.id}")
        return 0
    print(f"Failed to send: {item.id}", file=sys.stderr)
    return 1


def handle_inbox_stats(args: argparse.Namespace) -> int:
    del args
    items = cli_application().inbox.list()
    counts = {status: 0 for status in ("pending", "read", "dismissed", "resolved")}
    for item in items:
        counts[item.status] += 1
    print(f"Total:      {len(items)}")
    for status in ("pending", "read", "dismissed", "resolved"):
        print(f"{status.title() + ':':<11}{counts[status]}")
    return 0


def handle_inbox_clear(args: argparse.Namespace) -> int:
    status = cast(InboxClearStatus, args.status)
    count = cli_application().inbox.clear(status)
    print(f"Cleared {count} {status} Inbox item(s).")
    return 0


def handle_inbox_watch(args: argparse.Namespace) -> int:
    inbox = cli_application().inbox
    interval = max(1, args.interval)
    seen = {item.id for item in inbox.list()}
    print(f"Watching Inbox every {interval}s. Press Ctrl+C or type 'q' + Enter to quit.")
    try:
        while True:
            if _watch_stop_requested(interval):
                print("Stopped watching.")
                return 0
            for item in inbox.list(status="pending"):
                if item.id not in seen:
                    seen.add(item.id)
                    print_ansi(render_inbox_summary(item))
    except (KeyboardInterrupt, EOFError):
        print("\nStopped watching.")
        return 0


def _watch_stop_requested(interval: float) -> bool:
    try:
        readable, _, _ = select.select([sys.stdin], [], [], interval)
    except (OSError, ValueError):
        time.sleep(interval)
        return False
    if not readable:
        return False
    line = sys.stdin.readline()
    return line == "" or line.strip().casefold() == "q"
