"""Shared observable daemon lifecycle orchestration for CLI surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from nuself.daemon import lifecycle
from nuself.daemon.audit import write_lifecycle_audit
from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
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
    stage: Literal["start"] | None = None,
) -> None:
    """Project one authoritative daemon-start failure."""

    event = "start_failed" if operation == "start" else "restart_failed"
    write_lifecycle_audit(
        event,
        project_root=project_root,
        error=diagnostic_exception_chain(error),
        metadata={
            "reason": error.reason,
            "phase": error.status.phase,
            "pid": error.status.pid,
            "socket": str(error.status.socket_path),
            "exit_code": error.exit_code,
            **({"stage": stage} if stage is not None else {}),
        },
    )


def _write_stop_failure_audit(
    error: lifecycle.DaemonStopError,
    *,
    operation: Literal["stop", "restart"],
    project_root: Path | None,
    stage: Literal["stop"] | None = None,
) -> None:
    event = "stop_failed" if operation == "stop" else "restart_failed"
    write_lifecycle_audit(
        event,
        project_root=project_root,
        error=diagnostic_exception_chain(error),
        metadata={
            "reason": error.reason,
            "phase": error.status.phase,
            "pid": error.status.pid,
            "socket": str(error.status.socket_path),
            "owner_active": error.owner_active,
            **({"stage": stage} if stage is not None else {}),
        },
    )


def _start_result_metadata(
    result: lifecycle.DaemonStartResult,
) -> dict[str, object]:
    return {
        "outcome": result.outcome,
        "changed": result.changed,
        "from_phase": result.before.phase,
        "to_phase": result.status.phase,
        "pid": result.status.pid,
        "socket": str(result.status.socket_path),
    }


def _stop_result_metadata(
    result: lifecycle.DaemonStopResult,
) -> dict[str, object]:
    return {
        "outcome": result.outcome,
        "changed": result.changed,
        "from_phase": result.before.phase,
        "to_phase": result.status.phase,
        "pid": result.status.pid,
        "socket": str(result.status.socket_path),
    }


def start_daemon_observed(
    project_root: Path | None,
    *,
    initial_status: lifecycle.DaemonStatus | None = None,
) -> lifecycle.DaemonStartResult:
    """Run one daemon start with shared lifecycle projections."""

    write_lifecycle_audit(
        "start_requested",
        project_root=project_root,
    )
    try:
        if initial_status is None:
            result = lifecycle.start(project_root)
        else:
            result = lifecycle.start(
                project_root,
                initial_status=initial_status,
            )
    except lifecycle.DaemonStartError as exc:
        write_start_failure_audit(
            exc,
            operation="start",
            project_root=project_root,
        )
        raise
    write_lifecycle_audit(
        "start_completed",
        project_root=project_root,
        metadata=_start_result_metadata(result),
    )
    return result


def stop_daemon_observed(
    project_root: Path | None,
) -> lifecycle.DaemonStopResult:
    """Run one daemon stop with shared lifecycle projections."""

    write_lifecycle_audit(
        "stop_requested",
        project_root=project_root,
    )
    try:
        result = lifecycle.stop(project_root)
    except lifecycle.DaemonStopError as exc:
        _write_stop_failure_audit(
            exc,
            operation="stop",
            project_root=project_root,
        )
        raise
    write_lifecycle_audit(
        "stop_completed",
        project_root=project_root,
        metadata=_stop_result_metadata(result),
    )
    return result


def restart_daemon_observed(
    project_root: Path | None,
) -> lifecycle.DaemonRestartResult:
    """Run one ordered restart and project its combined outcome."""

    write_lifecycle_audit(
        "restart_requested",
        project_root=project_root,
    )
    try:
        stop_result = lifecycle.stop(project_root)
    except lifecycle.DaemonStopError as exc:
        _write_stop_failure_audit(
            exc,
            operation="restart",
            project_root=project_root,
            stage="stop",
        )
        raise
    try:
        start_result = lifecycle.start(
            project_root,
            initial_status=stop_result.status,
        )
    except lifecycle.DaemonStartError as exc:
        write_start_failure_audit(
            exc,
            operation="restart",
            project_root=project_root,
            stage="start",
        )
        raise
    result = lifecycle.DaemonRestartResult(
        stop=stop_result,
        start=start_result,
    )
    write_lifecycle_audit(
        "restart_completed",
        project_root=project_root,
        metadata={
            "stop_outcome": result.stop.outcome,
            "stop_changed": result.stop.changed,
            "stop_from_phase": result.stop.before.phase,
            "stop_to_phase": result.stop.status.phase,
            "start_outcome": result.start.outcome,
            "start_changed": result.start.changed,
            "start_from_phase": result.start.before.phase,
            "start_to_phase": result.start.status.phase,
            "pid": result.status.pid,
            "socket": str(result.status.socket_path),
        },
    )
    return result
