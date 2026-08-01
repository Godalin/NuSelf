"""Daemon command handlers and status rendering for the CLI."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.daemon_lifecycle import (
    format_lifecycle_failure,
    restart_daemon_observed,
    start_daemon_observed,
    stop_daemon_observed,
)
from nuself.cli.daemon_status import format_status, observe_daemon_status
from nuself.daemon import client, lifecycle
from nuself.runtime.diagnostics import diagnostic_exception_message


def format_daemon_list(status: lifecycle.DaemonStatus) -> str:
    pid = status.pid if status.pid is not None else "-"
    return "\n".join(
        [
            "name status pid socket",
            f"local {status.phase} {pid} {status.socket_path}",
        ]
    )


def handle_daemon_start(args: argparse.Namespace) -> int:
    try:
        result = start_daemon_observed(
            args.project_root,
        )
    except lifecycle.DaemonStartError as exc:
        print(
            f"Failed to start daemon: {format_lifecycle_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(format_status(result.status))
    return 0


def handle_daemon_stop(args: argparse.Namespace) -> int:
    try:
        result = stop_daemon_observed(
            args.project_root,
        )
    except lifecycle.DaemonStopError as exc:
        print(
            f"Failed to stop daemon: {format_lifecycle_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(format_status(result.status))
    return 0


def handle_daemon_restart(args: argparse.Namespace) -> int:
    try:
        result = restart_daemon_observed(args.project_root)
    except lifecycle.DaemonStopError as exc:
        print(
            f"Failed to restart daemon: {format_lifecycle_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    except lifecycle.DaemonStartError as exc:
        print(
            f"Failed to restart daemon: {format_lifecycle_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(
        "Restarted: "
        f"{format_status(result.status)} "
        f"stop={result.stop.outcome} start={result.start.outcome}"
    )
    return 0


def handle_daemon_status(args: argparse.Namespace) -> int:
    result = observe_daemon_status(args.project_root)
    if result is None:
        return 1
    print(format_status(result))
    return 0 if result.running else 1


def handle_daemon_health(args: argparse.Namespace) -> int:
    try:
        scheduler = client.health(
            project_root=args.project_root,
            timeout=2.0,
        )
    except (
        client.DaemonConnectionError,
        client.DaemonApplicationError,
    ) as exc:
        print(
            "Daemon health unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(
        "scheduler"
        f" running={str(scheduler.running).lower()}"
        f" accepting={str(scheduler.accepting).lower()}"
        f" pending={scheduler.pending}"
        f" in_flight={scheduler.in_flight}"
        f" capacity={scheduler.capacity}"
        f" last_error={scheduler.last_error or '-'}"
    )
    return 0


def handle_daemon_list(args: argparse.Namespace) -> int:
    result = observe_daemon_status(args.project_root)
    if result is None:
        return 1
    print(format_daemon_list(result))
    return 0
