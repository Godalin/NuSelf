"""Outer lifecycle owner for one authority-scoped application graph."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from threading import Lock
from types import TracebackType

from nuself.application.composition import (
    ApplicationGraph,
    compose_application,
)
from nuself.config import RuntimePaths, runtime_paths
from nuself.scope import NuSelfScope
from nuself.storage import ClosableStorageBackend, auto_backend
from nuself.storage_audit import report_backend_close_failure


class ApplicationRuntimeClosedError(RuntimeError):
    """Raised when application resources are requested after teardown."""


class ApplicationRuntime:
    """Lazily own one path/backend/graph tuple for a process surface."""

    def __init__(self, paths: RuntimePaths) -> None:
        self._paths = paths
        self._backend: ClosableStorageBackend | None = None
        self._application: ApplicationGraph | None = None
        self._closed = False
        self._lock = Lock()

    @property
    def paths(self) -> RuntimePaths:
        return self._paths

    @property
    def application(self) -> ApplicationGraph:
        with self._lock:
            self._require_open()
            if self._application is None:
                self._application = compose_application(
                    self._paths,
                    self._backend_locked(),
                )
            return self._application

    @property
    def backend(self) -> ClosableStorageBackend:
        """Borrow the runtime-owned backend for outer infrastructure adapters."""

        with self._lock:
            self._require_open()
            return self._backend_locked()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            backend = self._backend
            self._backend = None
            self._application = None
        if backend is None:
            return
        try:
            backend.close()
        except Exception as exc:
            report_backend_close_failure(
                exc,
                project_root=self._paths.authority_root,
                backend_type=type(backend).__name__,
            )
            raise

    def _require_open(self) -> None:
        if self._closed:
            raise ApplicationRuntimeClosedError(
                "application runtime is already closed"
            )

    def _backend_locked(self) -> ClosableStorageBackend:
        backend = self._backend
        if backend is None:
            backend = auto_backend(self._paths.authority_root)
            self._backend = backend
        return backend

    def __enter__(self) -> ApplicationRuntime:
        with self._lock:
            self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def open_application_runtime(
    authority: NuSelfScope | Path | None = None,
) -> ApplicationRuntime:
    """Resolve one authority without opening storage until first use."""

    return ApplicationRuntime(runtime_paths(authority))


_CURRENT_APPLICATION_RUNTIME: ContextVar[
    ApplicationRuntime | None
] = ContextVar("nuself_application_runtime", default=None)


def current_application_runtime() -> ApplicationRuntime | None:
    """Return the runtime borrowed by the current outer process scope."""

    return _CURRENT_APPLICATION_RUNTIME.get()


@contextmanager
def use_application_runtime(
    runtime: ApplicationRuntime,
) -> Generator[None]:
    """Make one runtime available to nested process adapters."""

    token: Token[ApplicationRuntime | None] = (
        _CURRENT_APPLICATION_RUNTIME.set(runtime)
    )
    try:
        yield
    finally:
        _CURRENT_APPLICATION_RUNTIME.reset(token)
