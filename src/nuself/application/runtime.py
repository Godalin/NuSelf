"""Outer lifecycle owner for one authority-scoped application graph."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
import threading
from types import TracebackType

from nuself.application.composition import (
    ApplicationGraph,
    compose_application,
)
from nuself.config import RuntimePaths, runtime_paths
from nuself.storage import (
    StorageBackend,
    get_default_backend,
)

class ApplicationRuntimeClosedError(RuntimeError):
    """Raised when application resources are requested after teardown."""


class ApplicationRuntime:
    """Lazily own one path/backend/graph tuple for a process surface."""

    def __init__(self, paths: RuntimePaths) -> None:
        self._paths = paths
        self._backend: StorageBackend | None = None
        self._application: ApplicationGraph | None = None
        self._closed = False
        self._lock = threading.RLock()

    @property
    def paths(self) -> RuntimePaths:
        return self._paths

    @property
    def application(self) -> ApplicationGraph:
        with self._lock:
            if self._closed:
                raise ApplicationRuntimeClosedError(
                    "application runtime is already closed"
                )
            if self._application is None:
                backend = get_default_backend(self._paths.project_root)
                self._backend = backend
                self._application = compose_application(
                    self._paths,
                    backend,
                )
            return self._application

    @property
    def opened(self) -> bool:
        with self._lock:
            return self._application is not None

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        from nuself import storage

        storage.reset_default_backend(self._paths.project_root)

    def __enter__(self) -> ApplicationRuntime:
        with self._lock:
            if self._closed:
                raise ApplicationRuntimeClosedError(
                    "application runtime is already closed"
                )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def open_application_runtime(
    project_root: Path | None = None,
) -> ApplicationRuntime:
    """Resolve one authority without opening storage until first use."""

    return ApplicationRuntime(runtime_paths(project_root))


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


def bind_application_runtime[T](callback: Callable[[], T]) -> Callable[[], T]:
    """Carry the current application authority into one owned worker call."""

    runtime = current_application_runtime()
    if runtime is None:
        return callback

    def bound() -> T:
        with use_application_runtime(runtime):
            return callback()

    return bound
