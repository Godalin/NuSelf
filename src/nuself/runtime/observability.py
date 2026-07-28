"""Observable boundaries for non-authoritative best-effort side effects."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
import warnings

from nuself.logs import LogComponent, write_log_event

T = TypeVar("T")


def format_exception_chain(exc: BaseException) -> str:
    """Return unique non-empty exception messages from outermost to root cause."""

    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)
        current = current.__cause__ or current.__context__
    return " <- ".join(messages) if messages else exc.__class__.__name__


def run_observed_best_effort(
    operation: Callable[[], T],
    *,
    component: LogComponent,
    event: str,
    message: str,
    project_root: Path | None = None,
    metadata: dict[str, object] | None = None,
) -> T | None:
    """Run a secondary effect without hiding its failure."""

    try:
        return operation()
    except Exception as exc:
        error = format_exception_chain(exc)
        try:
            write_log_event(
                component,
                event,
                message,
                project_root=project_root,
                level="warning",
                status="degraded",
                error=error,
                metadata=metadata,
            )
        except Exception as log_exc:
            warnings.warn(
                f"{component}/{event}: {error}; structured logging failed: "
                f"{format_exception_chain(log_exc)}",
                RuntimeWarning,
                stacklevel=2,
            )
        return None
