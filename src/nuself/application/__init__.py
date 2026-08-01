"""Application composition primitives shared by process adapters."""

from nuself.application.trace import TraceServices, compose_trace_services

__all__ = (
    "TraceServices",
    "compose_trace_services",
)
