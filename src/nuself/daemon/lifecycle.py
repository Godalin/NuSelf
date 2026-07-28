"""Daemon lifecycle helpers used by the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths
from nuself.daemon import client
from nuself.private_fs import ensure_private_file
from nuself.runtime.observability import report_corrupt_record


@dataclass(frozen=True)
class DaemonStatus:
    running: bool
    pid: int | None
    socket_path: Path
    pid_path: Path


def status(project_root: Path | None = None) -> DaemonStatus:
    paths = runtime_paths(project_root)
    pid = read_pid(paths)
    return DaemonStatus(
        running=client.ping(paths.project_root),
        pid=pid,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )


def start(project_root: Path | None = None) -> DaemonStatus:
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    current = status(paths.project_root)
    if current.running:
        return current
    ensure_private_file(paths.daemon_log_path)
    log_file = paths.daemon_log_path.open("ab")
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "nuself.daemon.server",
            "--project-root",
            str(paths.project_root),
        ],
        cwd=paths.project_root,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(40):
        time.sleep(0.05)
        current = status(paths.project_root)
        if current.running:
            return current
    return status(paths.project_root)


def stop(project_root: Path | None = None) -> DaemonStatus:
    paths = runtime_paths(project_root)
    if client.ping(paths.project_root):
        try:
            client.shutdown(paths.project_root)
        except (
            client.DaemonConnectionError,
            client.DaemonApplicationError,
        ):
            pass
    for _ in range(40):
        time.sleep(0.05)
        current = status(paths.project_root)
        if not current.running:
            return current
    pid = read_pid(paths)
    if pid is not None:
        os.kill(pid, signal.SIGTERM)
    return status(paths.project_root)


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
