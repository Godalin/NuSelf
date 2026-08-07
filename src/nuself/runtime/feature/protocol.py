"""Typed suspension protocol shared by Tool effect adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolEffectRequest(ABC):
    """Frontend-neutral request emitted by a suspending Tool effect."""

    component: str
    operation: str

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("Tool effect component must not be blank")
        if not self.operation.strip():
            raise ValueError("Tool effect operation must not be blank")

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return the stable wire discriminant for this request type."""


@dataclass(frozen=True)
class ToolEffectResolution(ABC):
    """Frontend-neutral resolution exactly bound to one request."""

    request: ToolEffectRequest

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return the stable wire discriminant for this resolution type."""


class ToolEffectPort(Protocol):
    """Resolve a structured Tool effect through one runtime adapter."""

    def resolve(
        self,
        request: ToolEffectRequest,
        *,
        on_requested: Callable[[], None],
    ) -> ToolEffectResolution: ...


class ToolEffectRequired(Exception):
    """Execution suspended until a frontend resolves one Tool effect."""

    def __init__(self, request: ToolEffectRequest) -> None:
        super().__init__(
            f"frontend effect resolution required for {request.operation}"
        )
        self.request = request


class RejectUnavailableEffectPort:
    """Fail closed when no interactive frontend is available."""

    def resolve(
        self,
        request: ToolEffectRequest,
        *,
        on_requested: Callable[[], None],
    ) -> ToolEffectResolution:
        on_requested()
        raise ToolEffectRequired(request)
