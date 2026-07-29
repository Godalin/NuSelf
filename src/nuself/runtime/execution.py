"""Owned one-shot execution and exact outcome transport."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
from typing import Generic, TypeVar, cast

from nuself.runtime.validation import validate_timeout

ResultT = TypeVar("ResultT")
_MISSING = object()


@dataclass(frozen=True, init=False)
class CallOutcome(Generic[ResultT]):
    """Exactly one value or escaping control/error object."""

    value: ResultT | None
    error: BaseException | None

    def __init__(
        self,
        *,
        value: ResultT | object = _MISSING,
        error: BaseException | None = None,
    ) -> None:
        if (value is _MISSING) == (error is None):
            raise ValueError("call outcome requires exactly one value or error")
        object.__setattr__(
            self,
            "value",
            None if value is _MISSING else cast(ResultT, value),
        )
        object.__setattr__(self, "error", error)


class OwnedCall(Generic[ResultT]):
    """Own one result-producing thread from start through completion."""

    def __init__(
        self,
        *,
        name: str,
        target: Callable[[], ResultT],
    ) -> None:
        if not callable(target):
            raise TypeError("owned call target must be callable")
        self._name = name
        self._target = target
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._outcome: CallOutcome[ResultT] | None = None

    def start(self) -> bool:
        """Start exactly once, rolling ownership back if thread start fails."""

        with self._lock:
            if self._thread is not None:
                return False
            thread = threading.Thread(
                target=self._run,
                name=self._name,
                daemon=False,
            )
            self._thread = thread
        try:
            thread.start()
        except BaseException:
            with self._lock:
                self._thread = None
            raise
        return True

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for completion, returning false only when the timeout expires."""

        _validate_timeout(timeout)
        return self._done.wait(timeout)

    def outcome(self, timeout: float | None = None) -> CallOutcome[ResultT]:
        """Return the completed outcome without translating its error."""

        if not self.wait(timeout):
            raise TimeoutError("owned call is still running")
        with self._lock:
            outcome = self._outcome
        if outcome is None:  # pragma: no cover - completion invariant
            raise RuntimeError("owned call completed without an outcome")
        return outcome

    @property
    def alive(self) -> bool:
        with self._lock:
            thread = self._thread
            return thread.is_alive() if thread is not None else False

    def _run(self) -> None:
        try:
            outcome = CallOutcome(value=self._target())
        except BaseException as exc:
            outcome = CallOutcome[ResultT](error=exc)
        with self._lock:
            self._outcome = outcome
        self._done.set()


def _validate_timeout(timeout: float | None) -> None:
    validate_timeout(
        timeout,
        field_name="owned call timeout",
        allow_none=True,
    )
