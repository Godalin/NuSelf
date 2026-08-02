"""Shared terminal watch loop for long-running reasoning steps."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from nuself.cli.output import print_ansi
from nuself.cli.composition import cli_application
from nuself.reason.errors import ReasonNotFound
from nuself.tui.reason import render_reason_detail, render_step_watch_entry
from nuself.tui.render import TerminalTheme

_theme = TerminalTheme()


def watch_reason_steps(
    project_root: Path | None,
    interval: int = 2,
    thread_ref: str | None = None,
) -> None:
    """Watch reasoning steps, optionally restricted to one thread."""
    service = cli_application().reason_service
    threads = service.list_threads(status="all")
    if thread_ref is not None:
        try:
            thread = service.show_thread(thread_ref)
        except ReasonNotFound:
            print(f"Reason thread not found: {thread_ref}", file=sys.stderr)
            return
        threads = [thread]
        print_ansi(render_reason_detail(thread))
        for step in service.list_steps(thread.id):
            print_ansi(render_step_watch_entry(step))
    else:
        for index, thread in enumerate(threads):
            print_ansi(render_reason_detail(thread))
            print_ansi(_theme.muted(f"(index: {index})"))
            for step in service.list_steps(thread.id):
                print_ansi(render_step_watch_entry(step))
    print()
    print("Watching for new reasoning steps. Press Ctrl+C to stop.")

    counts = {
        thread.id: len(service.list_steps(thread.id))
        for thread in threads
    }
    try:
        while True:
            time.sleep(interval)
            for thread in threads:
                steps = service.list_steps(thread.id)
                previous_count = counts.get(thread.id, 0)
                for step in steps[previous_count:]:
                    print_ansi(render_step_watch_entry(step))
                counts[thread.id] = len(steps)
    except KeyboardInterrupt:
        print("\nStopped watching.")
