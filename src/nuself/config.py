"""Project-level configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """Filesystem paths used by the local daemon and CLI."""

    project_root: Path
    private_root: Path
    runtime_dir: Path
    logs_dir: Path
    socket_path: Path
    pid_path: Path
    daemon_log_path: Path
    outbox_log_path: Path


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest project root containing AGENTS.md."""

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file():
            return candidate
    return current


def runtime_paths(project_root: Path | None = None) -> RuntimePaths:
    """Return conventional runtime paths under the ignored private root."""

    root = (project_root or find_project_root()).resolve()
    private_root = root / "private"
    runtime_dir = private_root / "runtime"
    logs_dir = private_root / "logs"
    return RuntimePaths(
        project_root=root,
        private_root=private_root,
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        socket_path=runtime_dir / "nuself.sock",
        pid_path=runtime_dir / "nuself.pid",
        daemon_log_path=logs_dir / "daemon.log",
        outbox_log_path=logs_dir / "outbox.log",
    )


def ensure_runtime_dirs(paths: RuntimePaths) -> None:
    """Create local ignored runtime directories."""

    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

