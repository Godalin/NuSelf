"""Domain-neutral ordered lifecycle cleanup execution."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nuself.runtime.diagnostics import diagnostic_exception_chain


@dataclass(frozen=True)
class CleanupFailure:
    """One named cleanup step and the exact failure it raised."""

    step: str
    error: BaseException


def run_cleanup_steps(
    steps: Sequence[tuple[str, Callable[[], object]]],
) -> tuple[CleanupFailure, ...]:
    """Attempt every named step once and retain failures in step order."""

    failures: list[CleanupFailure] = []
    for step, operation in steps:
        try:
            operation()
        except BaseException as exc:
            failures.append(CleanupFailure(step, exc))
    return tuple(failures)


def cleanup_failure_records(
    failures: Sequence[CleanupFailure],
) -> list[dict[str, object]]:
    """Project retained cleanup failures into ordered safe audit records."""

    return [
        {
            "step": failure.step,
            "error": diagnostic_exception_chain(failure.error),
        }
        for failure in failures
    ]
