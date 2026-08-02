"""One-shot system status, configuration, and log commands."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.output import print_ansi
from nuself.cli.application import cli_application
from nuself.cli.daemon_status import observe_daemon_status
from nuself.config import runtime_paths
from nuself.log.reader import read_log_events
from nuself.runtime.audit.types import LOG_COMPONENTS, LogComponent
from nuself.tui.render import render_log_event, render_log_event_json


def handle_status(args: argparse.Namespace) -> int:
    daemon = observe_daemon_status(args.project_root)
    if daemon is None:
        return 1
    application = cli_application()
    conversations = application.conversations.list()
    pending = len(
        application.notifications.list(status="pending")
    )
    print(f"daemon: {daemon.phase} pid={daemon.pid or '-'}")
    print(f"conversations: {len(conversations)}")
    print(f"pending notifications: {pending}")
    return 0


def handle_health(args: argparse.Namespace) -> int:
    issues: list[str] = []
    paths = runtime_paths(args.project_root)
    if not paths.authority_root.exists():
        issues.append(
            f"authority root missing: {paths.authority_root}"
        )
    daemon = observe_daemon_status(args.project_root)
    if daemon is not None and not daemon.running:
        issues.append(f"daemon is not ready: {daemon.phase}")
    if issues:
        print("Health issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    if daemon is None:
        return 1
    print("All checks passed.")
    return 0
def _component(value: object) -> LogComponent | None:
    if value in LOG_COMPONENTS:
        return value
    return None


def handle_logs(args: argparse.Namespace) -> int:
    component = _component(args.component)
    events = read_log_events(
        project_root=args.project_root,
        component=component,
        tail=max(args.tail, 1),
    )
    if not events:
        target = component or "any component"
        print(f"No logs found for {target}.")
        return 0
    for event in events:
        if args.json:
            print_ansi(render_log_event_json(event))
        else:
            print_ansi(
                render_log_event(
                    event,
                    color=False if args.no_color else None,
                )
            )
    if args.follow:
        print(
            "Log follow is not streaming yet; showing current "
            "tail only.",
            file=sys.stderr,
        )
    return 0
