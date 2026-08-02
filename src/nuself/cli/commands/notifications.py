"""One-shot notification outbox command handlers."""

from __future__ import annotations

import argparse
import select
import sys
import time
from typing import cast

from nuself.cli.output import print_ansi, resolve_handle
from nuself.cli.application import cli_application
from nuself.cli.exit_codes import CliExitCode
from nuself.notification.outbox import (
    NotificationOutbox,
    OutboxEntryNotFound,
)
from nuself.notification.model import NotificationClearStatus
from nuself.notification.composition import build_notification_adapters
from nuself.notification.delivery import deliver_entry_once
from nuself.tui.render import render_outbox_detail, render_outbox_summary


def _resolve_entry_id(
    args: argparse.Namespace,
    outbox: NotificationOutbox,
) -> str | None:
    return resolve_handle(
        args.entry_id,
        outbox.list(),
        label="notification",
        get_id=lambda entry: entry.id,
    )


def handle_notify_list(args: argparse.Namespace) -> int:
    status = args.status
    entries = cli_application().notifications.list(status=status)
    if not entries:
        filter_msg = f" with status '{status}'" if status else ""
        print(f"No outbox entries{filter_msg}.")
        return 0
    for index, entry in enumerate(entries):
        print_ansi(render_outbox_summary(entry, index=index))
    return 0


def handle_notify_show(args: argparse.Namespace) -> int:
    outbox = cli_application().notifications
    entry_id = _resolve_entry_id(args, outbox)
    if entry_id is None:
        return 1
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    print_ansi(render_outbox_detail(entry))
    return 0


def handle_notify_stats(args: argparse.Namespace) -> int:
    entries = cli_application().notifications.list()
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
    outbox = cli_application().notifications
    interval: float = max(1, args.interval)
    print(
        f"Watching outbox every {int(interval)}s. "
        "Press Ctrl+C or type 'q' + Enter to quit."
    )
    seen = {entry.id for entry in outbox.list()}
    try:
        while True:
            if _watch_stop_requested(interval):
                print("Stopped watching.")
                return CliExitCode.SUCCESS
            for entry in outbox.list():
                if entry.id not in seen:
                    seen.add(entry.id)
                    print_ansi(render_outbox_summary(entry))
    except KeyboardInterrupt:
        print("\nStopped watching.")
        return CliExitCode.SUCCESS


def _watch_stop_requested(interval: float) -> bool:
    """Wait for the next poll while honoring q and terminal EOF."""

    try:
        readable, _, _ = select.select([sys.stdin], [], [], interval)
    except (OSError, ValueError):
        time.sleep(interval)
        return False
    if not readable:
        return False
    line = sys.stdin.readline()
    return line == "" or line.strip().casefold() == "q"


def handle_notify_send(args: argparse.Namespace) -> int:
    application = cli_application()
    outbox = application.notifications
    entry_id = _resolve_entry_id(args, outbox)
    if entry_id is None:
        return 1
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    updated = deliver_entry_once(
        outbox,
        entry_id,
        build_notification_adapters(
            application.paths,
            email_config=application.config.email,
            macos_config=application.config.macos_notification,
        ),
    )
    if updated.status == "sent":
        print(f"Sent: {entry.id}")
        return 0
    print(f"Failed to send: {entry.id}", file=sys.stderr)
    return 1


def handle_notify_dismiss(args: argparse.Namespace) -> int:
    outbox = cli_application().notifications
    entry_id = _resolve_entry_id(args, outbox)
    if entry_id is None:
        return 1
    try:
        outbox.dismiss(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    print(f"Dismissed: {entry_id}")
    return 0


def handle_notify_clear(args: argparse.Namespace) -> int:
    selection = cast(NotificationClearStatus, args.status)
    count = cli_application().notifications.clear(selection)
    print(f"Cleared {count} {selection} notification(s).")
    return 0
