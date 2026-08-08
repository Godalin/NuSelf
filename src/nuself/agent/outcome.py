"""Immutable framework Tool execution outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from nuself.runtime.feature.effect import Execution
from nuself.runtime.messages import freeze_json_value


@dataclass(frozen=True)
class ToolOutcome:
    """One detached Tool execution result shared by runtime consumers."""

    name: str
    execution: Execution
    args: Mapping[str, object]
    result: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Tool outcome name must not be blank")
        if (self.result is None) == (self.error is None):
            raise ValueError(
                "Tool outcome requires exactly one of result or error"
            )
        value = self.result if self.result is not None else self.error
        if value is None or not value.strip():
            raise ValueError("Tool outcome result or error must not be blank")
        frozen = freeze_json_value(dict(self.args))
        if not isinstance(frozen, Mapping):
            raise TypeError("Tool outcome args must be a mapping")
        object.__setattr__(self, "args", cast(Mapping[str, object], frozen))

    @property
    def succeeded(self) -> bool:
        return self.error is None


class ToolOutcomeProjection(Protocol):
    """Non-raising projection boundary for framework Tool outcomes."""

    def project_best_effort(
        self,
        outcome: ToolOutcome,
        *,
        service_component: str,
    ) -> None: ...

    def report_capture_failure(
        self,
        error: Exception,
        *,
        tool: str,
    ) -> None: ...


__all__ = ["ToolOutcome", "ToolOutcomeProjection"]
