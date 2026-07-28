"""Cross-process ownership for one project daemon."""

from __future__ import annotations

from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import IO, Literal

from nuself.private_fs import ensure_private_file


class DaemonInstanceLockContended(RuntimeError):
    """Raised when another process owns the project daemon."""


class DaemonInstanceLockCleanupError(RuntimeError):
    """A lock operation and its required handle close both failed."""

    def __init__(
        self,
        operation: Literal["acquire", "release"],
        *,
        primary_error: BaseException,
        cleanup_error: BaseException,
    ) -> None:
        super().__init__(
            f"daemon instance lock {operation} and handle cleanup both failed"
        )
        self.operation = operation
        self.primary_error = primary_error
        self.cleanup_error = cleanup_error


class DaemonInstanceLock:
    """Hold a stable advisory lock for one daemon lifecycle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        ensure_private_file(self.path)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            flock(handle.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            primary_error = DaemonInstanceLockContended(
                "another daemon owns this project runtime"
            )
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise DaemonInstanceLockCleanupError(
                    "acquire",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise primary_error from None
        except BaseException as primary_error:
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise DaemonInstanceLockCleanupError(
                    "acquire",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            flock(handle.fileno(), LOCK_UN)
        except BaseException as primary_error:
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise DaemonInstanceLockCleanupError(
                    "release",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise
        else:
            handle.close()

    def __enter__(self) -> DaemonInstanceLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.release()
