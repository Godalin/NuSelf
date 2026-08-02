"""Daemon lifecycle helpers used by the CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal, Never

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths
from nuself.daemon import client
from nuself.daemon.instance import daemon_instance_owned
from nuself.private_fs import ensure_private_file
from nuself.scope import NuSelfScope
from nuself.runtime.observability import report_corrupt_record
from nuself.runtime.warning import (
    TerminalWarningDefinition,
    TerminalWarningRegistry,
    TerminalWarningSchemaError,
    emit_registered_terminal_warning,
)

DAEMON_PROCESS_LOG_ROTATION_FAILED = (
    "daemon/process_log_rotation_failed"
)


def _validate_process_log_rotation_warning(
    metadata: Mapping[str, object],
) -> None:
    error_type = metadata["error_type"]
    if not isinstance(error_type, str) or not error_type.strip():
        raise TerminalWarningSchemaError(
            "daemon process-log warning error_type must be non-blank"
        )


def _build_daemon_lifecycle_warning_registry() -> TerminalWarningRegistry:
    return (
        TerminalWarningRegistry()
        .register(
            TerminalWarningDefinition(
                DAEMON_PROCESS_LOG_ROTATION_FAILED,
                ("error_type",),
                _validate_process_log_rotation_warning,
                suffix="continuing startup",
            )
        )
        .seal()
    )


DAEMON_LIFECYCLE_WARNING_REGISTRY = (
    _build_daemon_lifecycle_warning_registry()
)


@dataclass(frozen=True)
class DaemonProcessLogRetentionPolicy:
    """Startup-time retention for the inherited raw daemon stream."""

    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 3

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("daemon process log max_bytes must be positive")
        if self.backup_count < 1:
            raise ValueError("daemon process log backup_count must be positive")


DEFAULT_DAEMON_PROCESS_LOG_RETENTION = DaemonProcessLogRetentionPolicy()


@dataclass(frozen=True)
class DaemonWaitPolicy:
    """One positive finite monotonic lifecycle wait policy."""

    timeout_seconds: float = 2.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        for name, value in (
            ("timeout_seconds", self.timeout_seconds),
            ("poll_interval_seconds", self.poll_interval_seconds),
        ):
            if isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError(
                    f"daemon lifecycle {name} must be positive and finite"
                )


DEFAULT_DAEMON_STARTUP_POLICY = DaemonWaitPolicy()
DEFAULT_DAEMON_SHUTDOWN_POLICY = DaemonWaitPolicy(timeout_seconds=30.0)
DAEMON_CONTROL_PROBE_TIMEOUT_SECONDS = 2.0

type DaemonStartFailureReason = Literal[
    "spawn_failed",
    "status_failed",
    "owner_unready",
    "process_exited",
    "timeout",
]
type DaemonStopFailureReason = Literal[
    "request_failed",
    "ownership_check_failed",
    "timeout",
]
type DaemonPhase = Literal[
    "stopped",
    "owned_unready",
    "ready",
    "inconsistent",
    "unknown",
]


@dataclass(frozen=True)
class DaemonStatus:
    phase: DaemonPhase
    pid: int | None
    socket_path: Path
    pid_path: Path

    def __post_init__(self) -> None:
        if self.phase != "ready" and self.pid is not None:
            raise ValueError("only a ready daemon status may carry a PID")

    @property
    def running(self) -> bool:
        return self.phase == "ready"

    @property
    def owner_active(self) -> bool | None:
        if self.phase == "unknown":
            return None
        return self.phase in {"owned_unready", "ready"}


type DaemonStartOutcome = Literal["started", "already_ready"]
type DaemonStopOutcome = Literal["stopped", "already_stopped"]


@dataclass(frozen=True)
class DaemonStartResult:
    before: DaemonStatus
    status: DaemonStatus
    outcome: DaemonStartOutcome

    def __post_init__(self) -> None:
        _validate_transition_runtime(self.before, self.status)
        if self.status.phase != "ready":
            raise ValueError("a successful daemon start must end ready")
        if self.outcome == "already_ready" and self.before.phase != "ready":
            raise ValueError("already_ready requires a ready initial status")
        if self.outcome == "started" and self.before.phase == "ready":
            raise ValueError("started requires a non-ready initial status")

    @property
    def changed(self) -> bool:
        return self.outcome == "started"


@dataclass(frozen=True)
class DaemonStopResult:
    before: DaemonStatus
    status: DaemonStatus
    outcome: DaemonStopOutcome

    def __post_init__(self) -> None:
        _validate_transition_runtime(self.before, self.status)
        if self.status.phase != "stopped":
            raise ValueError("a successful daemon stop must end stopped")
        if (
            self.outcome == "already_stopped"
            and self.before.phase != "stopped"
        ):
            raise ValueError(
                "already_stopped requires a stopped initial status"
            )
        if self.outcome == "stopped" and self.before.phase == "stopped":
            raise ValueError("stopped requires a non-stopped initial status")

    @property
    def changed(self) -> bool:
        return self.outcome == "stopped"


@dataclass(frozen=True)
class DaemonRestartResult:
    stop: DaemonStopResult
    start: DaemonStartResult

    def __post_init__(self) -> None:
        if self.start.before != self.stop.status:
            raise ValueError(
                "daemon restart start must consume the stop result status"
            )


def _validate_transition_runtime(
    before: DaemonStatus,
    status: DaemonStatus,
) -> None:
    if (
        before.socket_path != status.socket_path
        or before.pid_path != status.pid_path
    ):
        raise ValueError(
            "daemon transition statuses belong to different runtimes"
        )


class DaemonStatusError(RuntimeError):
    """Daemon ownership could not be observed authoritatively."""

    def __init__(self, status: DaemonStatus) -> None:
        super().__init__("daemon ownership status could not be observed")
        self.status = status


class DaemonStartError(RuntimeError):
    """A spawned daemon could not become ready."""

    def __init__(
        self,
        reason: DaemonStartFailureReason,
        *,
        status: DaemonStatus,
        exit_code: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if reason == "spawn_failed":
            message = "daemon process could not be spawned"
        elif reason == "status_failed":
            message = "daemon status could not be observed"
        elif reason == "owner_unready":
            message = "daemon owns the runtime but is not ready"
        elif reason == "process_exited":
            message = (
                "daemon process exited before becoming ready "
                f"(exit_code={exit_code})"
            )
        else:
            message = (
                "daemon did not become ready within "
                f"{timeout_seconds:g} seconds"
            )
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.exit_code = exit_code
        self.timeout_seconds = timeout_seconds


class DaemonStopError(RuntimeError):
    """A daemon could not complete graceful ownership release."""

    def __init__(
        self,
        reason: DaemonStopFailureReason,
        *,
        status: DaemonStatus,
        timeout_seconds: float | None = None,
    ) -> None:
        if reason == "request_failed":
            message = "daemon rejected the shutdown request"
        elif reason == "ownership_check_failed":
            message = "daemon ownership could not be verified"
        else:
            message = (
                "daemon did not stop and release ownership within "
                f"{timeout_seconds:g} seconds"
            )
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.timeout_seconds = timeout_seconds

def status(
    project_root: Path | None = None,
    *,
    ping_timeout: float = 2.0,
) -> DaemonStatus:
    paths = runtime_paths(project_root)
    running = client.ping(
        paths.authority_root,
        timeout=ping_timeout,
    )
    partial = DaemonStatus(
        phase="unknown",
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    try:
        owned = daemon_instance_owned(paths.daemon_lock_path)
    except Exception as exc:
        raise DaemonStatusError(partial) from exc
    phase: DaemonPhase
    if running:
        phase = "ready" if owned else "inconsistent"
    else:
        phase = "owned_unready" if owned else "stopped"
    return DaemonStatus(
        phase=phase,
        pid=read_pid(paths) if phase == "ready" else None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )


def start(
    authority: NuSelfScope | Path | None = None,
    *,
    initial_status: DaemonStatus | None = None,
    process_log_retention: DaemonProcessLogRetentionPolicy = (
        DEFAULT_DAEMON_PROCESS_LOG_RETENTION
    ),
    startup_policy: DaemonWaitPolicy = DEFAULT_DAEMON_STARTUP_POLICY,
) -> DaemonStartResult:
    paths = runtime_paths(authority)
    if initial_status is None:
        ensure_runtime_dirs(paths)
        current = _status_for_start(paths.authority_root)
    else:
        _validate_status_paths(initial_status, paths)
        ensure_runtime_dirs(paths)
        current = initial_status
    if current.running:
        return DaemonStartResult(
            before=current,
            status=current,
            outcome="already_ready",
        )
    before = current
    if current.phase == "owned_unready":
        raise DaemonStartError(
            "owner_unready",
            status=current,
        )
    if current.phase in {"inconsistent", "unknown"}:
        raise DaemonStartError(
            "status_failed",
            status=current,
        )
    try:
        _rotate_daemon_process_log_if_needed(
            paths.daemon_process_log_path,
            process_log_retention,
        )
    except OSError as exc:
        emit_registered_terminal_warning(
            DAEMON_LIFECYCLE_WARNING_REGISTRY,
            DAEMON_PROCESS_LOG_ROTATION_FAILED,
            {"error_type": type(exc).__name__},
            stacklevel=2,
        )
    ensure_private_file(paths.daemon_process_log_path)
    with paths.daemon_process_log_path.open("ab") as process_log:
        try:
            command = [
                sys.executable,
                "-m",
                "nuself.daemon.server",
                "--user-root",
                str(paths.scope.user_root),
            ]
            if paths.scope.workspace_root is not None:
                command.extend(
                    [
                        "--workspace-root",
                        str(paths.scope.workspace_root),
                    ]
                )
            process = subprocess.Popen(
                command,
                cwd=paths.authority_root,
                stdout=process_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            raise DaemonStartError(
                "spawn_failed",
                status=current,
            ) from exc
    deadline = time.monotonic() + startup_policy.timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        current = _status_for_start(
            paths.authority_root,
            ping_timeout=remaining,
        )
        if current.running:
            return DaemonStartResult(
                before=before,
                status=current,
                outcome="started",
            )
        exit_code = process.poll()
        if exit_code is not None:
            raise DaemonStartError(
                "process_exited",
                status=current,
                exit_code=exit_code,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(startup_policy.poll_interval_seconds, remaining))
    raise DaemonStartError(
        "timeout",
        status=current,
        timeout_seconds=startup_policy.timeout_seconds,
    )


def _status_for_start(
    project_root: Path,
    *,
    ping_timeout: float = 2.0,
) -> DaemonStatus:
    try:
        return status(project_root, ping_timeout=ping_timeout)
    except DaemonStatusError as exc:
        raise DaemonStartError(
            "status_failed",
            status=exc.status,
        ) from exc


def _validate_status_paths(
    status_snapshot: DaemonStatus,
    paths: RuntimePaths,
) -> None:
    if (
        status_snapshot.socket_path != paths.socket_path
        or status_snapshot.pid_path != paths.pid_path
    ):
        raise ValueError(
            "initial daemon status belongs to a different runtime project"
        )


def _rotate_daemon_process_log_if_needed(
    path: Path,
    policy: DaemonProcessLogRetentionPolicy,
) -> None:
    if not path.exists() or path.stat().st_size < policy.max_bytes:
        return
    ensure_private_file(path)
    for index in range(1, policy.backup_count + 1):
        backup = _daemon_process_log_backup(path, index)
        if backup.exists():
            ensure_private_file(backup)
    oldest = _daemon_process_log_backup(path, policy.backup_count)
    oldest.unlink(missing_ok=True)
    for index in range(policy.backup_count - 1, 0, -1):
        source = _daemon_process_log_backup(path, index)
        if source.exists():
            source.replace(_daemon_process_log_backup(path, index + 1))
    path.replace(_daemon_process_log_backup(path, 1))


def _daemon_process_log_backup(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")


def stop(
    project_root: Path | None = None,
    *,
    shutdown_policy: DaemonWaitPolicy = DEFAULT_DAEMON_SHUTDOWN_POLICY,
) -> DaemonStopResult:
    paths = runtime_paths(project_root)
    deadline = time.monotonic() + shutdown_policy.timeout_seconds
    current = _status_for_stop(
        paths.authority_root,
        ping_timeout=min(
            DAEMON_CONTROL_PROBE_TIMEOUT_SECONDS,
            shutdown_policy.timeout_seconds,
        ),
    )
    owner_active = current.owner_active
    assert owner_active is not None
    if not current.running and not owner_active:
        return DaemonStopResult(
            before=current,
            status=current,
            outcome="already_stopped",
        )
    before = current
    request_error: client.DaemonConnectionError | None = None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _raise_daemon_stop_timeout(
            current,
            policy=shutdown_policy,
            request_error=None,
        )
    try:
        client.shutdown(
            paths.authority_root,
            timeout=min(
                DAEMON_CONTROL_PROBE_TIMEOUT_SECONDS,
                remaining,
            ),
        )
    except client.DaemonApplicationError as exc:
        raise DaemonStopError(
            "request_failed",
            status=current,
        ) from exc
    except client.DaemonConnectionError as exc:
        request_error = exc
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        current = _status_for_stop(
            paths.authority_root,
            ping_timeout=min(
                DAEMON_CONTROL_PROBE_TIMEOUT_SECONDS,
                remaining,
            ),
        )
        owner_active = current.owner_active
        assert owner_active is not None
        if not current.running and not owner_active:
            return DaemonStopResult(
                before=before,
                status=current,
                outcome="stopped",
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(shutdown_policy.poll_interval_seconds, remaining))
    _raise_daemon_stop_timeout(
        current,
        policy=shutdown_policy,
        request_error=request_error,
    )


def _raise_daemon_stop_timeout(
    status_snapshot: DaemonStatus,
    *,
    policy: DaemonWaitPolicy,
    request_error: client.DaemonConnectionError | None,
) -> Never:
    error = DaemonStopError(
        "timeout",
        status=status_snapshot,
        timeout_seconds=policy.timeout_seconds,
    )
    if request_error is not None:
        raise error from request_error
    raise error


def _status_for_stop(
    project_root: Path,
    *,
    ping_timeout: float,
) -> DaemonStatus:
    try:
        return status(project_root, ping_timeout=ping_timeout)
    except DaemonStatusError as exc:
        raise DaemonStopError(
            "ownership_check_failed",
            status=exc.status,
        ) from exc


def read_pid(paths: RuntimePaths) -> int | None:
    try:
        raw_pid = paths.pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not raw_pid.isascii() or not raw_pid.isdecimal():
        _report_invalid_pid(paths)
        return None
    pid = int(raw_pid)
    if pid <= 0:
        _report_invalid_pid(paths)
        return None
    return pid


def _report_invalid_pid(paths: RuntimePaths) -> None:
    report_corrupt_record(
        ValueError("daemon PID metadata is invalid"),
        component="daemon",
        collection="daemon_runtime",
        record_id=paths.pid_path.stem,
        project_root=paths.authority_root,
    )
