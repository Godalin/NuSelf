"""Explicit process-signal ownership for one daemon lifecycle."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType

type SignalHandler = int | Callable[[int, FrameType | None], object]


@dataclass(frozen=True)
class SignalRestorationFailure:
    """One signal whose prior handler could not be restored."""

    signal_number: int
    error: Exception


class DaemonSignalRestoreError(RuntimeError):
    """Raised after every still-owned signal restoration was attempted."""

    def __init__(
        self,
        failures: tuple[SignalRestorationFailure, ...],
    ) -> None:
        super().__init__(
            f"failed to restore {len(failures)} daemon signal handler(s)"
        )
        self.failures = failures


class DaemonSignalInstallCleanupError(RuntimeError):
    """Raised when signal installation and its rollback both fail."""

    def __init__(
        self,
        failures: tuple[SignalRestorationFailure, ...],
    ) -> None:
        super().__init__(
            "daemon signal installation failed and rollback was incomplete"
        )
        self.failures = failures


class DaemonSignalOwner:
    """Borrow SIGINT/SIGTERM and restore the exact prior handlers."""

    _SIGNALS = (signal.SIGINT, signal.SIGTERM)

    def __init__(self, shutdown_requested: threading.Event) -> None:
        self._shutdown_requested = shutdown_requested
        self._owned: dict[int, SignalHandler] = {}

    def install(self) -> bool:
        """Install both handlers, rolling back a partial installation."""

        if len(self._owned) == len(self._SIGNALS):
            return False
        if self._owned:
            raise RuntimeError(
                "daemon signal owner has an incomplete prior installation"
            )
        try:
            for signal_number in self._SIGNALS:
                previous = signal.getsignal(signal_number)
                if previous is None:
                    raise RuntimeError(
                        f"signal {signal_number} has no restorable handler"
                    )
                signal.signal(signal_number, self._handle_signal)
                self._owned[signal_number] = previous
        except Exception as install_error:
            failures = self._restore_owned()
            if failures:
                raise DaemonSignalInstallCleanupError(
                    failures
                ) from install_error
            raise
        return True

    def restore(self) -> bool:
        """Restore every still-owned signal in reverse installation order."""

        if not self._owned:
            return False
        failures = self._restore_owned()
        if failures:
            raise DaemonSignalRestoreError(failures)
        return True

    def _restore_owned(
        self,
    ) -> tuple[SignalRestorationFailure, ...]:
        failures: list[SignalRestorationFailure] = []
        for signal_number in reversed(tuple(self._owned)):
            previous = self._owned[signal_number]
            try:
                signal.signal(signal_number, previous)
            except Exception as exc:
                failures.append(
                    SignalRestorationFailure(signal_number, exc)
                )
            else:
                self._owned.pop(signal_number)
        return tuple(failures)

    def _handle_signal(
        self,
        signal_number: int,
        frame: FrameType | None,
    ) -> None:
        del signal_number, frame
        self._shutdown_requested.set()
