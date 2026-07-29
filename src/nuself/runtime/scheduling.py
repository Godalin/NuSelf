"""Owned delayed callback scheduling with atomic lifecycle cleanup."""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from math import isfinite


class DelayedTaskScheduler:
    """Own distinct delayed callbacks until execution or shutdown."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._closed = False
        self._timers: dict[Hashable, threading.Timer] = {}

    def schedule(
        self,
        key: Hashable,
        delay_seconds: float,
        callback: Callable[[], None],
    ) -> bool:
        """Schedule one unique key, returning false when closed or duplicate."""

        if (
            isinstance(delay_seconds, bool)
            or not isfinite(delay_seconds)
            or delay_seconds < 0
        ):
            raise ValueError(
                "delayed task delay must be finite and non-negative"
            )
        if not callable(callback):
            raise TypeError("delayed task callback must be callable")
        with self._lock:
            if self._closed or key in self._timers:
                return False
            timer = threading.Timer(
                delay_seconds,
                self._run,
                args=(key, callback),
            )
            timer.daemon = True
            self._timers[key] = timer
            try:
                timer.start()
            except BaseException:
                self._timers.pop(key, None)
                timer.cancel()
                raise
            return True

    def _run(
        self,
        key: Hashable,
        callback: Callable[[], None],
    ) -> None:
        with self._lock:
            timer = self._timers.pop(key, None)
            if timer is None or self._closed:
                return
            callback()

    def close(self) -> int:
        """Close scheduling, cancel owned timers, and return the cancel count."""

        with self._lock:
            if self._closed:
                return 0
            self._closed = True
            timers = tuple(self._timers.values())
            self._timers.clear()
            for timer in timers:
                timer.cancel()
            return len(timers)

    def contains(self, key: Hashable) -> bool:
        with self._lock:
            return key in self._timers

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._timers)
