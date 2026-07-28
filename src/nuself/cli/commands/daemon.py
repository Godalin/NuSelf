"""Daemon command handlers and status rendering for the CLI."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.daemon_lifecycle import (
    format_start_failure,
    format_stop_failure,
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
            f"Failed to start daemon: {format_start_failure(exc)}",
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
            f"Failed to stop daemon: {format_stop_failure(exc)}",
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
            f"Failed to restart daemon: {format_stop_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    except lifecycle.DaemonStartError as exc:
        print(
            f"Failed to restart daemon: {format_start_failure(exc)}",
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
        response = client.health(
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
    for worker in response.workers:
        print(
            "worker"
            f" name={worker.name}"
            f" alive={str(worker.alive).lower()}"
            f" failures={worker.consecutive_failures}"
            f" last_success={worker.last_success_at or '-'}"
            f" last_error={worker.last_error or '-'}"
        )
    return 0


def handle_daemon_list(args: argparse.Namespace) -> int:
    result = observe_daemon_status(args.project_root)
    if result is None:
        return 1
    print(format_daemon_list(result))
    return 0
