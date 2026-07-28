"""Daemon command handlers and status rendering for the CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from nuself.daemon import client, lifecycle
from nuself.daemon.audit import write_lifecycle_audit
from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
)


def format_status(status: lifecycle.DaemonStatus) -> str:
    pid = status.pid if status.pid is not None else "-"
    return f"daemon {status.phase} pid={pid} socket={status.socket_path}"


def format_daemon_list(status: lifecycle.DaemonStatus) -> str:
    pid = status.pid if status.pid is not None else "-"
    return "\n".join(
        [
            "name status pid socket",
            f"local {status.phase} {pid} {status.socket_path}",
        ]
    )


def format_start_failure(error: lifecycle.DaemonStartError) -> str:
    """Render one safe daemon-start failure across CLI surfaces."""

    return diagnostic_exception_message(error)


def format_stop_failure(error: lifecycle.DaemonStopError) -> str:
    """Render one safe daemon-stop failure across CLI surfaces."""

    return diagnostic_exception_message(error)


def write_start_failure_audit(
    error: lifecycle.DaemonStartError,
    *,
    operation: Literal["start", "restart"],
    project_root: Path | None,
) -> None:
    """Project one authoritative daemon-start failure."""

    write_lifecycle_audit(
        f"{operation}_failed",
        f"daemon {operation} failed",
        project_root=project_root,
        level="error",
        status="error",
        error=diagnostic_exception_chain(error),
        metadata={
            "reason": error.reason,
            "phase": error.status.phase,
            "pid": error.status.pid,
            "socket": str(error.status.socket_path),
            "exit_code": error.exit_code,
        },
    )


def start_daemon_observed(
    project_root: Path | None,
    *,
    operation: Literal["start", "restart"],
) -> lifecycle.DaemonStatus:
    """Run one daemon start with shared lifecycle projections."""

    if operation == "start":
        write_lifecycle_audit(
            f"{operation}_requested",
            f"daemon {operation} requested",
            project_root=project_root,
        )
    try:
        result = lifecycle.start(project_root)
    except lifecycle.DaemonStartError as exc:
        write_start_failure_audit(
            exc,
            operation=operation,
            project_root=project_root,
        )
        raise
    write_lifecycle_audit(
        f"{operation}_completed",
        f"daemon {operation} {'completed' if result.running else 'failed'}",
        project_root=project_root,
        status=result.phase,
        metadata={"pid": result.pid, "socket": str(result.socket_path)},
    )
    return result


def stop_daemon_observed(
    project_root: Path | None,
    *,
    operation: Literal["stop", "restart"],
) -> lifecycle.DaemonStatus:
    """Run one daemon stop with shared lifecycle projections."""

    if operation == "stop":
        write_lifecycle_audit(
            "stop_requested",
            "daemon stop requested",
            project_root=project_root,
        )
    try:
        result = lifecycle.stop(project_root)
    except lifecycle.DaemonStopError as exc:
        write_lifecycle_audit(
            f"{operation}_failed",
            f"daemon {operation} failed",
            project_root=project_root,
            level="error",
            status="error",
            error=diagnostic_exception_chain(exc),
            metadata={
                "reason": exc.reason,
                "phase": exc.status.phase,
                "pid": exc.status.pid,
                "socket": str(exc.status.socket_path),
                "owner_active": exc.owner_active,
            },
        )
        raise
    if operation == "stop":
        write_lifecycle_audit(
            "stop_completed",
            f"daemon stop {'completed' if not result.running else 'failed'}",
            project_root=project_root,
            status="stopped" if not result.running else "running",
            metadata={"pid": result.pid, "socket": str(result.socket_path)},
        )
    return result


def handle_daemon_start(args: argparse.Namespace) -> int:
    try:
        result = start_daemon_observed(
            args.project_root,
            operation="start",
        )
    except lifecycle.DaemonStartError as exc:
        print(
            f"Failed to start daemon: {format_start_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(format_status(result))
    return 0 if result.running else 1


def handle_daemon_stop(args: argparse.Namespace) -> int:
    try:
        result = stop_daemon_observed(
            args.project_root,
            operation="stop",
        )
    except lifecycle.DaemonStopError as exc:
        print(
            f"Failed to stop daemon: {format_stop_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(format_status(result))
    return 0 if not result.running else 1


def handle_daemon_restart(args: argparse.Namespace) -> int:
    write_lifecycle_audit(
        "restart_requested",
        "daemon restart requested",
        project_root=args.project_root,
    )
    try:
        stop_result = stop_daemon_observed(
            args.project_root,
            operation="restart",
        )
    except lifecycle.DaemonStopError as exc:
        print(
            f"Failed to restart daemon: {format_stop_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    if stop_result.running:
        print(
            f"Failed to stop daemon: {format_status(stop_result)}",
            file=sys.stderr,
        )
        return 1
    print(f"Stopped: {format_status(stop_result)}")
    try:
        start_result = start_daemon_observed(
            args.project_root,
            operation="restart",
        )
    except lifecycle.DaemonStartError as exc:
        print(
            f"Failed to restart daemon: {format_start_failure(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Started: {format_status(start_result)}")
    return 0 if start_result.running else 1


def handle_daemon_status(args: argparse.Namespace) -> int:
    try:
        result = lifecycle.status(args.project_root)
    except lifecycle.DaemonStatusError as exc:
        print(
            "Daemon status unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
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
    try:
        result = lifecycle.status(args.project_root)
    except lifecycle.DaemonStatusError as exc:
        print(
            "Daemon status unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(format_daemon_list(result))
    return 0
