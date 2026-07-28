"""One-shot notification outbox command handlers."""

from __future__ import annotations

import argparse
import sys
import time

from nuself.commands.output import print_ansi, resolve_handle
from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationOutbox,
    OutboxEntryNotFound,
)
from nuself.tui.render import render_outbox_detail, render_outbox_summary


def _resolve_entry_id(args: argparse.Namespace) -> str | None:
    return resolve_handle(
        args.entry_id,
        NotificationOutbox(args.project_root).list(),
        label="notification",
        get_id=lambda entry: entry.id,
    )


def handle_notify_list(args: argparse.Namespace) -> int:
    status = args.status
    entries = NotificationOutbox(args.project_root).list(status=status)
    if not entries:
        filter_msg = f" with status '{status}'" if status else ""
        print(f"No outbox entries{filter_msg}.")
        return 0
    for index, entry in enumerate(entries):
        print_ansi(render_outbox_summary(entry, index=index))
    return 0


def handle_notify_show(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = NotificationOutbox(args.project_root).get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    print_ansi(render_outbox_detail(entry))
    return 0


def handle_notify_stats(args: argparse.Namespace) -> int:
    entries = NotificationOutbox(args.project_root).list()
    counts: dict[str, int] = {
        "pending": 0,
        "sent": 0,
        "failed": 0,
        "dismissed": 0,
    }
    for entry in entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
    print(f"Total:      {len(entries)}")
    print(f"Pending:    {counts['pending']}")
    print(f"Sent:       {counts['sent']}")
    print(f"Failed:     {counts['failed']}")
    print(f"Dismissed:  {counts['dismissed']}")
    return 0


def handle_notify_watch(args: argparse.Namespace) -> int:
    outbox = NotificationOutbox(args.project_root)
    interval: float = max(1, args.interval)
    print(
        f"Watching outbox every {int(interval)}s. "
        "Press Ctrl+C or type 'q' + Enter to quit."
    )
    seen = {entry.id for entry in outbox.list()}
    try:
        while True:
            time.sleep(interval)
            for entry in outbox.list():
                if entry.id not in seen:
                    seen.add(entry.id)
                    print_ansi(render_outbox_summary(entry))
    except KeyboardInterrupt:
        print("\nStopped watching.")
        return 0


def handle_notify_send(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    outbox = NotificationOutbox(args.project_root)
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    if LogOnlyNotificationAdapter(args.project_root).send(entry):
        outbox.mark_sent(entry_id)
        print(f"Sent: {entry.id}")
        return 0
    outbox.mark_failed(entry_id)
    print(f"Failed to send: {entry.id}", file=sys.stderr)
    return 1


def handle_notify_dismiss(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        NotificationOutbox(args.project_root).dismiss(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    print(f"Dismissed: {entry_id}")
    return 0


def handle_notify_clear(args: argparse.Namespace) -> int:
    count = NotificationOutbox(args.project_root).clear("dismissed")
    print(f"Cleared {count} dismissed notification(s).")
    return 0
