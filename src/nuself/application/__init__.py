"""Application composition primitives shared by process adapters."""

from nuself.application.authority import (
    AuthorityRuntime,
    AuthorityRuntimeClosedError,
    open_authority_runtime,
)

__all__ = (
    "AuthorityRuntime",
    "AuthorityRuntimeClosedError",
    "open_authority_runtime",
)
