"""Explicit ownership of one selected authority's neutral resources."""

from __future__ import annotations

from pathlib import Path
import threading
from types import TracebackType

from nuself.config import RuntimePaths, runtime_paths
from nuself.storage import ClosableStorageBackend, auto_backend


class AuthorityRuntimeClosedError(RuntimeError):
    """Raised when a closed authority runtime is used."""


class AuthorityRuntime:
    """Own resolved paths and storage for one authority lifetime."""

    def __init__(
        self,
        paths: RuntimePaths,
        backend: ClosableStorageBackend,
    ) -> None:
        self._paths = paths
        self._backend = backend
        self._closed = False
        self._close_lock = threading.Lock()

    @property
    def paths(self) -> RuntimePaths:
        with self._close_lock:
            self._require_open()
            return self._paths

    @property
    def backend(self) -> ClosableStorageBackend:
        with self._close_lock:
            self._require_open()
            return self._backend

    @property
    def closed(self) -> bool:
        with self._close_lock:
            return self._closed

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._backend.close()

    def __enter__(self) -> AuthorityRuntime:
        with self._close_lock:
            self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise AuthorityRuntimeClosedError(
                "authority runtime is already closed"
            )


def open_authority_runtime(
    project_root: Path | None = None,
) -> AuthorityRuntime:
    """Resolve and open the neutral resources for one authority."""

    paths = runtime_paths(project_root)
    return AuthorityRuntime(paths, auto_backend(paths.project_root))
