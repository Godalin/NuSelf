"""Shared typed failures for framework-native agent invocation."""

from __future__ import annotations


class AgentError(RuntimeError):
    """Base class for failures owned by the shared agent boundary."""


class AgentModelUnavailableError(AgentError):
    """Raised when no configured model endpoint can serve the capability."""


class AgentProtocolError(AgentError):
    """Raised when the framework response envelope violates its contract."""


class AgentInvalidOutputError(AgentError):
    """Raised when generated output is empty or violates the requested schema."""
