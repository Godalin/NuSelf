"""Typed ownership for one daemon background thread."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
from typing import Literal

WorkerLifecycleState = Literal["new", "running", "stopped", "timed_out"]


@dataclass(frozen=True)
class WorkerLifecycleSnapshot:
    name: str
    state: WorkerLifecycleState
    alive: bool


class OwnedWorker:
    """Own exactly one startable daemon thread."""

    def __init__(
        self,
        *,
        name: str,
        thread_name: str,
        target: Callable[[], None],
    ) -> None:
        self.name = name
        self._thread_name = thread_name
        self._target = target
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: WorkerLifecycleState = "new"

    @property
    def snapshot(self) -> WorkerLifecycleSnapshot:
        with self._lock:
            thread = self._thread
            return WorkerLifecycleSnapshot(
                name=self.name,
                state=self._state,
                alive=thread.is_alive() if thread is not None else False,
            )

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None:
                return False
            thread = threading.Thread(
                target=self._run,
                name=self._thread_name,
                daemon=True,
            )
            self._thread = thread
            self._state = "running"
        try:
            thread.start()
        except BaseException:
            with self._lock:
                self._thread = None
                self._state = "new"
            raise
        return True

    def join(self, timeout: float = 5.0) -> WorkerLifecycleSnapshot:
        with self._lock:
            thread = self._thread
        if thread is None:
            return self.snapshot
        thread.join(timeout=timeout)
        with self._lock:
            if thread.is_alive():
                self._state = "timed_out"
            elif self._state != "stopped":
                self._state = "stopped"
            return WorkerLifecycleSnapshot(
                name=self.name,
                state=self._state,
                alive=thread.is_alive(),
            )

    def _run(self) -> None:
        try:
            self._target()
        finally:
            with self._lock:
                self._state = "stopped"
