"""Project-level configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
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


def load_project_env(project_root: Path | None = None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from the ignored root .env file."""

    root = (project_root or find_project_root()).resolve()
    env_path = root / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key == "":
            continue
        result[key] = _strip_env_value(value.strip())
    return result


def config_value(name: str, default: str, project_root: Path | None = None) -> str:
    """Read a setting from the process environment, then project .env."""

    value = os.environ.get(name)
    if value is not None:
        return value
    return load_project_env(project_root).get(name, default)


def config_int(name: str, default: int, project_root: Path | None = None) -> int:
    """Read an integer setting with a safe fallback."""

    raw = config_value(name, str(default), project_root)
    try:
        value = int(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
