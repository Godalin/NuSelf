"""Owned one-shot execution and exact outcome transport."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import Context, ContextVar, Token, copy_context
from dataclasses import dataclass
from math import isfinite
import threading
from typing import Generator, Generic, TypeVar, cast

ResultT = TypeVar("ResultT")
_MISSING = object()
CancelCallback = Callable[[], None]


def validate_timeout(
    value: float | None,
    *,
    field_name: str,
    allow_none: bool,
) -> float | None:
    """Return one finite non-negative execution timeout."""

    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} must be finite and non-negative")
    if (
        isinstance(value, bool)
        or type(value) not in {int, float}
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{field_name} must be finite and non-negative")
    return float(value)


class CancellationCleanupError(RuntimeError):
    """Raised after every cancellation closer was attempted."""

    def __init__(self, failures: tuple[BaseException, ...]) -> None:
        super().__init__(
            f"owned call cancellation failed in {len(failures)} closer(s)"
        )
        self.failures = failures


class CancellationToken:
    """Thread-safe cooperative cancellation shared with one owned call."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[CancelCallback] = []

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> bool:
        """Request cancellation once and invoke every registered closer."""

        with self._lock:
            if self._cancelled.is_set():
                return False
            self._cancelled.set()
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        failures: list[BaseException] = []
        for callback in callbacks:
            try:
                callback()
            except BaseException as exc:
                failures.append(exc)
        if failures:
            raise CancellationCleanupError(tuple(failures))
        return True

    def register(self, callback: CancelCallback) -> Callable[[], None]:
        """Register a cancellation closer and return its removal callback."""

        with self._lock:
            if not self._cancelled.is_set():
                self._callbacks.append(callback)
                return lambda: self._discard(callback)
        callback()
        return lambda: None

    def _discard(self, callback: CancelCallback) -> None:
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass


_CURRENT_CANCELLATION: ContextVar[CancellationToken | None] = ContextVar(
    "nuself_current_cancellation",
    default=None,
)


def current_cancellation() -> CancellationToken | None:
    """Return the cooperative cancellation token for the current call."""

    return _CURRENT_CANCELLATION.get()


@contextmanager
def use_cancellation(
    cancellation: CancellationToken,
) -> Generator[CancellationToken, None, None]:
    """Bind one cancellation token for nested transport operations."""

    binding: Token[CancellationToken | None] = (
        _CURRENT_CANCELLATION.set(cancellation)
    )
    try:
        yield cancellation
    finally:
        _CURRENT_CANCELLATION.reset(binding)


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
        cancellation: CancellationToken | None = None,
    ) -> None:
        if not callable(target):
            raise TypeError("owned call target must be callable")
        self._name = name
        self._target = target
        self._context: Context = copy_context()
        self._cancellation = cancellation or CancellationToken()
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
                target=self._run_in_context,
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

    def cancel(self) -> bool:
        """Request cooperative cancellation of the owned call."""

        return self._cancellation.cancel()

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
            with use_cancellation(self._cancellation):
                outcome = CallOutcome(value=self._target())
        except BaseException as exc:
            outcome = CallOutcome[ResultT](error=exc)
        with self._lock:
            self._outcome = outcome
        self._done.set()

    def _run_in_context(self) -> None:
        self._context.run(self._run)


def _validate_timeout(timeout: float | None) -> None:
    validate_timeout(
        timeout,
        field_name="owned call timeout",
        allow_none=True,
    )
