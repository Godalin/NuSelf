"""Application composition primitives shared by process adapters."""

from nuself.application.profile import compose_profile_repository
from nuself.application.trace import TraceServices, compose_trace_services

__all__ = (
    "TraceServices",
    "compose_profile_repository",
    "compose_trace_services",
)
