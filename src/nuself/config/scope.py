"""Explicit user and workspace authority selection."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Literal, Mapping

type ScopeKind = Literal["user", "workspace"]

_AUTHORITY_ID_VERSION = "v1"
_DEFAULT_HOME_NAME = ".nuself"


class ScopeSelectionError(ValueError):
    """Raised when CLI or environment scope selection is invalid."""


@dataclass(frozen=True)
class NuSelfScope:
    """One canonical and isolated NuSelf state authority."""

    kind: ScopeKind
    root: Path
    authority_id: str
    user_root: Path
    workspace_root: Path | None = None

    def __post_init__(self) -> None:
        if not self.root.is_absolute() or not self.user_root.is_absolute():
            raise ValueError("scope roots must be absolute")
        if self.kind == "user" and self.root != self.user_root:
            raise ValueError("user scope root must equal its user root")
        if self.kind == "user" and self.workspace_root is not None:
            raise ValueError("user scope cannot have a workspace root")
        if self.kind == "workspace":
            if self.workspace_root is None:
                raise ValueError("workspace scope requires a workspace root")
            if not self.workspace_root.is_absolute():
                raise ValueError("workspace root must be absolute")
            if self.root != self.workspace_root / _DEFAULT_HOME_NAME:
                raise ValueError(
                    "workspace authority root must be <workspace>/.nuself"
                )


@dataclass(frozen=True)
class RuntimePaths:
    """All paths derived from one already-selected authority."""

    scope: NuSelfScope
    authority_root: Path
    config_file: Path
    user_config_file: Path
    database_file: Path
    sources_dir: Path
    logs_dir: Path
    exports_dir: Path
    imports_dir: Path
    runtime_dir: Path
    socket_runtime_dir: Path
    socket_path: Path
    pid_path: Path
    daemon_lock_path: Path
    daemon_log_path: Path
    daemon_process_log_path: Path
    outbox_log_path: Path

def resolve_scope(
    *,
    local: bool = False,
    workspace: Path | None = None,
    cwd: Path | None = None,
    user_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> NuSelfScope:
    """Resolve one explicit authority without repository discovery."""

    if local and workspace is not None:
        raise ScopeSelectionError(
            "--local and --workspace cannot be used together"
        )

    current = _canonical(cwd or Path.cwd())
    environment = os.environ if environ is None else environ
    user_root = _resolve_user_root(
        user_home=user_home,
        environ=environment,
    )
    if local or workspace is not None:
        workspace_root = _canonical(workspace or current)
        authority_root = workspace_root / _DEFAULT_HOME_NAME
        return NuSelfScope(
            kind="workspace",
            root=authority_root,
            workspace_root=workspace_root,
            user_root=user_root,
            authority_id=_authority_id(authority_root),
        )

    return NuSelfScope(
        kind="user",
        root=user_root,
        user_root=user_root,
        authority_id=_authority_id(user_root),
    )


def resolve_runtime_paths(scope: NuSelfScope) -> RuntimePaths:
    """Derive the complete filesystem contract from one scope."""

    root = scope.root
    runtime_dir = root / "runtime"
    logs_dir = root / "logs"
    socket_runtime_dir = _socket_runtime_dir()
    return RuntimePaths(
        scope=scope,
        authority_root=root,
        config_file=root / "config.yaml",
        user_config_file=scope.user_root / "config.yaml",
        database_file=root / "nuself.sqlite",
        sources_dir=root / "sources",
        logs_dir=logs_dir,
        exports_dir=root / "exports",
        imports_dir=root / "imports",
        runtime_dir=runtime_dir,
        socket_runtime_dir=socket_runtime_dir,
        socket_path=socket_runtime_dir / f"{scope.authority_id}.sock",
        pid_path=runtime_dir / "nuself.pid",
        daemon_lock_path=runtime_dir / "nuself.lock",
        daemon_log_path=logs_dir / "daemon.log",
        daemon_process_log_path=logs_dir / "daemon-process.log",
        outbox_log_path=logs_dir / "outbox.log",
    )


def scope_from_authority_root(root: Path) -> NuSelfScope:
    """Construct a scope for an already-resolved internal authority root."""

    authority_root = root.expanduser().absolute()
    return NuSelfScope(
        kind="user",
        root=authority_root,
        user_root=authority_root,
        authority_id=_authority_id(authority_root),
    )


def _resolve_user_root(
    *,
    user_home: Path | None,
    environ: Mapping[str, str],
) -> Path:
    configured_home = environ.get("NUSELF_HOME")
    if configured_home is not None:
        if not configured_home.strip():
            raise ScopeSelectionError("NUSELF_HOME cannot be blank")
        raw_root = Path(configured_home).expanduser()
        if not raw_root.is_absolute():
            raise ScopeSelectionError("NUSELF_HOME must be an absolute path")
        return _canonical(raw_root)
    home = _canonical(user_home or Path.home())
    return home / _DEFAULT_HOME_NAME


def _socket_runtime_dir() -> Path:
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        candidate = Path(xdg_runtime).expanduser()
        if candidate.is_absolute():
            return candidate / "nuself"
    return Path(tempfile.gettempdir()) / f"nuself-{os.getuid()}"


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _authority_id(root: Path) -> str:
    identity = f"{_AUTHORITY_ID_VERSION}\0{root}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:24]
    return f"{_AUTHORITY_ID_VERSION}-{digest}"
