"""Declared reason-domain failures."""

from __future__ import annotations


class ReasonError(Exception):
    """Base class for expected reason subsystem failures."""


class ReasonNotFound(ReasonError):
    """Raised when a reason thread or step cannot be resolved."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"reason not found: {identifier}")


class ReasonPromptError(ReasonError):
    """Raised when a reasoning prompt cannot be produced."""


class ReasonAdvanceError(ReasonError):
    """Raised when a reasoning thread cannot perform one advance."""


class ReasonTransitionError(ReasonError):
    """Raised when a requested reason status transition is invalid."""


class ReasonOperationConflict(ReasonError):
    """A durable operation key was reused for different input."""
