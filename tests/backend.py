"""Pytest-scoped storage ownership for direct repository tests."""

from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path

from nuself.config import runtime_paths
from nuself.storage import ClosableStorageBackend, StorageBackend, auto_backend

_BACKENDS: ContextVar[dict[Path, StorageBackend] | None] = ContextVar(
    "nuself_owned_backends",
    default=None,
)


def begin_backend_scope() -> Token[dict[Path, StorageBackend] | None]:
    return _BACKENDS.set({})


def end_backend_scope(
    token: Token[dict[Path, StorageBackend] | None],
) -> None:
    backends = _BACKENDS.get()
    _BACKENDS.reset(token)
    if backends is None:
        return
    failures: list[BaseException] = []
    for backend in backends.values():
        if not isinstance(backend, ClosableStorageBackend):
            continue
        try:
            backend.close()
        except BaseException as exc:
            failures.append(exc)
    if failures:
        raise BaseExceptionGroup("test backend cleanup failed", failures)


def owned_backend(project_root: Path | None) -> StorageBackend:
    backends = _require_scope()
    root = runtime_paths(project_root).authority_root
    backend = backends.get(root)
    if backend is None:
        backend = auto_backend(root)
        backends[root] = backend
    return backend


def close_owned_backend(project_root: Path) -> None:
    backend = _require_scope().pop(
        runtime_paths(project_root).authority_root,
        None,
    )
    if isinstance(backend, ClosableStorageBackend):
        backend.close()


def _require_scope() -> dict[Path, StorageBackend]:
    backends = _BACKENDS.get()
    if backends is None:
        raise RuntimeError("test backend scope is not active")
    return backends
