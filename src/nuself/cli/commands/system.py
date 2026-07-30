"""One-shot system status, configuration, and log commands."""

from __future__ import annotations

import argparse
import sys

from nuself.agent.chat import ThreadStore
from nuself.cli.commands.output import print_ansi
from nuself.cli.daemon_status import observe_daemon_status
from nuself.config import ConfigSystem, runtime_paths
from nuself.logs import (
    LOG_COMPONENTS,
    LogComponent,
    read_log_events,
)
from nuself.notification import NotificationOutbox
from nuself.tui.render import render_log_event, render_log_event_json


def handle_status(args: argparse.Namespace) -> int:
    daemon = observe_daemon_status(args.project_root)
    if daemon is None:
        return 1
    threads = ThreadStore(args.project_root).list()
    pending = len(
        NotificationOutbox(args.project_root).list(
            status="pending"
        )
    )
    print(f"daemon: {daemon.phase} pid={daemon.pid or '-'}")
    print(f"threads: {len(threads)}")
    print(f"pending notifications: {pending}")
    return 0


def handle_health(args: argparse.Namespace) -> int:
    issues: list[str] = []
    paths = runtime_paths(args.project_root)
    if not paths.authority_root.exists():
        issues.append(
            f"authority root missing: {paths.authority_root}"
        )
    status_unavailable = False
    daemon = observe_daemon_status(args.project_root)
    if daemon is None:
        status_unavailable = True
    else:
        if not daemon.running:
            issues.append(f"daemon is not ready: {daemon.phase}")
    if issues:
        print("Health issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    if status_unavailable:
        return 1
    print("All checks passed.")
    return 0


def handle_config(args: argparse.Namespace) -> int:
    paths = runtime_paths(args.project_root)
    config_path = paths.authority_root / "config.yaml"
    print(f"authority_root: {paths.authority_root}")
    print(f"socket_path: {paths.socket_path}")
    print(f"config_path: {config_path}")
    state = (
        "found"
        if config_path.exists()
        else "not found (using defaults)"
    )
    print(f"config_file: {state}")
    print("daemon_reload: restart required after configuration changes")
    effective = ConfigSystem.load(
        config_path, args.project_root
    )
    print("config_effective:")
    for key, value in sorted(
        ConfigSystem().as_flat_dict(effective).items()
    ):
        print(f"  {key}: {value}")
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
