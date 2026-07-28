"""Daemon lifecycle helpers used by the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal, Never

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths
from nuself.daemon import client
from nuself.daemon.instance import (
    DaemonInstanceLock,
    DaemonInstanceLockContended,
)
from nuself.private_fs import ensure_private_file
from nuself.runtime.diagnostics import emit_runtime_warning
from nuself.runtime.observability import report_corrupt_record


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
DEFAULT_DAEMON_SHUTDOWN_POLICY = DaemonWaitPolicy()

DaemonStartFailureReason = Literal[
    "spawn_failed",
    "process_exited",
    "timeout",
]
DaemonStopFailureReason = Literal[
    "request_failed",
    "ownership_check_failed",
    "timeout",
]


@dataclass(frozen=True)
class DaemonStatus:
    running: bool
    pid: int | None
    socket_path: Path
    pid_path: Path


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
        owner_active: bool | None,
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
        self.owner_active = owner_active
        self.timeout_seconds = timeout_seconds


def status(
    project_root: Path | None = None,
    *,
    ping_timeout: float = 2.0,
) -> DaemonStatus:
    paths = runtime_paths(project_root)
    running = client.ping(
        paths.project_root,
        timeout=ping_timeout,
    )
    return DaemonStatus(
        running=running,
        pid=read_pid(paths) if running else None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )


def start(
    project_root: Path | None = None,
    *,
    process_log_retention: DaemonProcessLogRetentionPolicy = (
        DEFAULT_DAEMON_PROCESS_LOG_RETENTION
    ),
    startup_policy: DaemonWaitPolicy = DEFAULT_DAEMON_STARTUP_POLICY,
) -> DaemonStatus:
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    current = status(paths.project_root)
    if current.running:
        return current
    try:
        _rotate_daemon_process_log_if_needed(
            paths.daemon_process_log_path,
            process_log_retention,
        )
    except OSError as exc:
        emit_runtime_warning(
            "daemon/process_log_rotation_failed: "
            f"error_type={type(exc).__name__}; continuing startup",
            stacklevel=2,
        )
    ensure_private_file(paths.daemon_process_log_path)
    with paths.daemon_process_log_path.open("ab") as process_log:
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "nuself.daemon.server",
                    "--project-root",
                    str(paths.project_root),
                ],
                cwd=paths.project_root,
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
            raise DaemonStartError(
                "timeout",
                status=current,
                timeout_seconds=startup_policy.timeout_seconds,
            )
        current = status(
            paths.project_root,
            ping_timeout=remaining,
        )
        if current.running:
            return current
        exit_code = process.poll()
        if exit_code is not None:
            raise DaemonStartError(
                "process_exited",
                status=current,
                exit_code=exit_code,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DaemonStartError(
                "timeout",
                status=current,
                timeout_seconds=startup_policy.timeout_seconds,
            )
        time.sleep(min(startup_policy.poll_interval_seconds, remaining))


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
) -> DaemonStatus:
    paths = runtime_paths(project_root)
    deadline = time.monotonic() + shutdown_policy.timeout_seconds
    current = status(
        paths.project_root,
        ping_timeout=shutdown_policy.timeout_seconds,
    )
    owner_active = _inspect_daemon_ownership(paths, current)
    if not current.running and not owner_active:
        return current
    request_error: client.DaemonConnectionError | None = None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _raise_daemon_stop_timeout(
            current,
            owner_active=owner_active,
            policy=shutdown_policy,
            request_error=None,
        )
    try:
        client.shutdown(
            paths.project_root,
            timeout=remaining,
        )
    except client.DaemonApplicationError as exc:
        raise DaemonStopError(
            "request_failed",
            status=current,
            owner_active=owner_active,
        ) from exc
    except client.DaemonConnectionError as exc:
        request_error = exc
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _raise_daemon_stop_timeout(
                current,
                owner_active=owner_active,
                policy=shutdown_policy,
                request_error=request_error,
            )
        current = status(
            paths.project_root,
            ping_timeout=remaining,
        )
        owner_active = _inspect_daemon_ownership(paths, current)
        if not current.running and not owner_active:
            return current
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _raise_daemon_stop_timeout(
                current,
                owner_active=owner_active,
                policy=shutdown_policy,
                request_error=request_error,
            )
        time.sleep(min(shutdown_policy.poll_interval_seconds, remaining))


def _raise_daemon_stop_timeout(
    status_snapshot: DaemonStatus,
    *,
    owner_active: bool,
    policy: DaemonWaitPolicy,
    request_error: client.DaemonConnectionError | None,
) -> Never:
    error = DaemonStopError(
        "timeout",
        status=status_snapshot,
        owner_active=owner_active,
        timeout_seconds=policy.timeout_seconds,
    )
    if request_error is not None:
        raise error from request_error
    raise error


def _inspect_daemon_ownership(
    paths: RuntimePaths,
    status_snapshot: DaemonStatus,
) -> bool:
    lock = DaemonInstanceLock(paths.daemon_lock_path)
    try:
        with lock:
            pass
    except DaemonInstanceLockContended:
        return True
    except Exception as exc:
        raise DaemonStopError(
            "ownership_check_failed",
            status=status_snapshot,
            owner_active=None,
        ) from exc
    return False


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
        project_root=paths.project_root,
    )
