"""Mixed proactive inbox view."""

import argparse

from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi
from nuself.tui.render import render_outbox_summary, render_reflection_entry_summary


def handle_inbox(args: argparse.Namespace) -> int:
    """Render pending items across proactive domains."""

    del args
    application = cli_application()
    reflections = application.reflection.service.list_entries(status="pending")
    notifications = application.notifications.list(status="pending")
    if not reflections and not notifications:
        print("Inbox is empty.")
        return 0
    if reflections:
        print("Pending reflections:")
        for index, entry in enumerate(reflections):
            print_ansi(render_reflection_entry_summary(entry, index=index))
    if notifications:
        if reflections:
            print()
        print("Pending notifications:")
        for index, entry in enumerate(notifications):
            print_ansi(render_outbox_summary(entry, index=index))
    return 0
