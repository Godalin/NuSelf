"""Cross-process ownership for one project daemon."""

from __future__ import annotations

from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import IO


class DaemonInstanceLockContended(RuntimeError):
    """Raised when another process owns the project daemon."""


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            flock(handle.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise DaemonInstanceLockContended(
                "another daemon owns this project runtime"
            ) from None
        except Exception:
            handle.close()
            raise
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            flock(handle.fileno(), LOCK_UN)
        finally:
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
