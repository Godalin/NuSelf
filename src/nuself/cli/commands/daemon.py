"""Daemon command handlers and status rendering for the CLI."""

from __future__ import annotations

import argparse
import sys

from nuself.daemon import client, lifecycle
from nuself.daemon.audit import write_lifecycle_audit
from nuself.runtime.diagnostics import diagnostic_exception_message


def format_status(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return f"daemon {state} pid={pid} socket={status.socket_path}"


def format_daemon_list(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return "\n".join(
        [
            "name status pid socket",
            f"local {state} {pid} {status.socket_path}",
        ]
    )


def handle_daemon_start(args: argparse.Namespace) -> int:
    write_lifecycle_audit(
        "start_requested",
        "daemon start requested",
        project_root=args.project_root,
    )
    result = lifecycle.start(args.project_root)
    write_lifecycle_audit(
        "start_completed",
        f"daemon start {'completed' if result.running else 'failed'}",
        project_root=args.project_root,
        status="running" if result.running else "stopped",
        metadata={"pid": result.pid, "socket": str(result.socket_path)},
    )
    print(format_status(result))
    return 0 if result.running else 1


def handle_daemon_stop(args: argparse.Namespace) -> int:
    write_lifecycle_audit(
        "stop_requested",
        "daemon stop requested",
        project_root=args.project_root,
    )
    result = lifecycle.stop(args.project_root)
    write_lifecycle_audit(
        "stop_completed",
        f"daemon stop {'completed' if not result.running else 'failed'}",
        project_root=args.project_root,
        status="stopped" if not result.running else "running",
        metadata={"pid": result.pid, "socket": str(result.socket_path)},
    )
    print(format_status(result))
    return 0 if not result.running else 1


def handle_daemon_restart(args: argparse.Namespace) -> int:
    write_lifecycle_audit(
        "restart_requested",
        "daemon restart requested",
        project_root=args.project_root,
    )
    stop_result = lifecycle.stop(args.project_root)
    if stop_result.running:
        print(
            f"Failed to stop daemon: {format_status(stop_result)}",
            file=sys.stderr,
        )
        return 1
    print(f"Stopped: {format_status(stop_result)}")
    start_result = lifecycle.start(args.project_root)
    write_lifecycle_audit(
        "restart_completed",
        f"daemon restart {'completed' if start_result.running else 'failed'}",
        project_root=args.project_root,
        status="running" if start_result.running else "stopped",
        metadata={
            "pid": start_result.pid,
            "socket": str(start_result.socket_path),
        },
    )
    print(f"Started: {format_status(start_result)}")
    return 0 if start_result.running else 1


def handle_daemon_status(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
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
    result = lifecycle.status(args.project_root)
    print(format_daemon_list(result))
    return 0
