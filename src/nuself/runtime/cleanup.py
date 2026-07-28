"""Domain-neutral ordered lifecycle cleanup execution."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


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
