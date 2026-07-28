"""Neutral correlation context shared by runtime boundaries."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeContext:
    """Correlation identifiers inherited across one logical operation."""

    thread_id: str | None = None
    request_id: str | None = None
    turn_id: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    source: str | None = None

    def to_record(self) -> dict[str, str]:
        """Return populated context fields as a serializable record."""

        return {
            key: value
            for key, value in (
                ("thread_id", self.thread_id),
                ("request_id", self.request_id),
                ("turn_id", self.turn_id),
                ("job_id", self.job_id),
                ("trace_id", self.trace_id),
                ("source", self.source),
            )
            if value is not None
        }


_CURRENT_RUNTIME_CONTEXT: ContextVar[RuntimeContext | None] = ContextVar(
    "nuself_runtime_context",
    default=None,
)


def current_runtime_context() -> RuntimeContext:
    """Return the correlation context for the current execution context."""

    return _CURRENT_RUNTIME_CONTEXT.get() or RuntimeContext()


@contextmanager
def runtime_context(
    *,
    thread_id: str | None = None,
    request_id: str | None = None,
    turn_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    source: str | None = None,
) -> Generator[RuntimeContext, None, None]:
    """Temporarily extend the current correlation context."""

    previous = current_runtime_context()
    merged = RuntimeContext(
        thread_id=thread_id if thread_id is not None else previous.thread_id,
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
