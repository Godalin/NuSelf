"""Neutral correlation context shared by runtime boundaries."""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

_CONTEXT_FIELDS = frozenset(
    {
        "conversation_id",
        "reason_id",
        "request_id",
        "turn_id",
        "job_id",
        "trace_id",
        "source",
    }
)


@dataclass(frozen=True)
class RuntimeContext:
    """Correlation identifiers inherited across one logical operation."""

    conversation_id: str | None = None
    reason_id: str | None = None
    request_id: str | None = None
    turn_id: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        for field_name in _CONTEXT_FIELDS:
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(
                    f"runtime context {field_name} must be a non-blank string"
                )

    def to_record(self) -> dict[str, str]:
        """Return populated context fields as a serializable record."""

        return {
            key: value
            for key, value in (
                ("conversation_id", self.conversation_id),
                ("reason_id", self.reason_id),
                ("request_id", self.request_id),
                ("turn_id", self.turn_id),
                ("job_id", self.job_id),
                ("trace_id", self.trace_id),
                ("source", self.source),
            )
            if value is not None
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> RuntimeContext:
        """Decode one detached context, including the pre-v0.3.1 alias."""

        normalized = dict(record)
        legacy_thread_id = normalized.pop("thread_id", None)
        if legacy_thread_id is not None:
            if "conversation_id" in normalized:
                raise ValueError(
                    "runtime context cannot contain both thread_id and "
                    "conversation_id"
                )
            normalized["conversation_id"] = legacy_thread_id
        unknown = set(normalized) - _CONTEXT_FIELDS
        if unknown:
            raise ValueError(
                f"runtime context has unknown fields: {sorted(unknown)!r}"
            )
        values: dict[str, str] = {}
        for field_name, value in normalized.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"runtime context {field_name} must be a non-blank string"
                )
            values[field_name] = value
        return cls(
            conversation_id=values.get("conversation_id"),
            reason_id=values.get("reason_id"),
            request_id=values.get("request_id"),
            turn_id=values.get("turn_id"),
            job_id=values.get("job_id"),
            trace_id=values.get("trace_id"),
            source=values.get("source"),
        )


_CURRENT_RUNTIME_CONTEXT: ContextVar[RuntimeContext | None] = ContextVar(
    "nuself_runtime_context",
    default=None,
)


def current_runtime_context() -> RuntimeContext:
    """Return the correlation context for the current execution context."""

    return _CURRENT_RUNTIME_CONTEXT.get() or RuntimeContext()


@contextmanager
def use_runtime_context(
    context: RuntimeContext,
) -> Generator[RuntimeContext, None, None]:
    """Temporarily replace the ambient context with one saved context."""

    token: Token[RuntimeContext | None] = _CURRENT_RUNTIME_CONTEXT.set(
        context
    )
    try:
        yield context
    finally:
        _CURRENT_RUNTIME_CONTEXT.reset(token)


def bind_runtime_context(
    callback: Callable[P, R],
) -> Callable[P, R]:
    """Bind one callback to the context active at wrapper creation."""

    captured = current_runtime_context()

    @wraps(callback)
    def bound(*args: P.args, **kwargs: P.kwargs) -> R:
        with use_runtime_context(captured):
            return callback(*args, **kwargs)

    return bound


@contextmanager
def runtime_context(
    *,
    conversation_id: str | None = None,
    reason_id: str | None = None,
    request_id: str | None = None,
    turn_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    source: str | None = None,
) -> Generator[RuntimeContext, None, None]:
    """Temporarily extend the current correlation context."""

    previous = current_runtime_context()
    merged = RuntimeContext(
        conversation_id=(
            conversation_id
            if conversation_id is not None
            else previous.conversation_id
        ),
        reason_id=reason_id if reason_id is not None else previous.reason_id,
        request_id=request_id if request_id is not None else previous.request_id,
        turn_id=turn_id if turn_id is not None else previous.turn_id,
        job_id=job_id if job_id is not None else previous.job_id,
        trace_id=trace_id if trace_id is not None else previous.trace_id,
        source=source if source is not None else previous.source,
    )
    token: Token[RuntimeContext | None] = _CURRENT_RUNTIME_CONTEXT.set(merged)
    try:
        yield merged
    finally:
        _CURRENT_RUNTIME_CONTEXT.reset(token)
