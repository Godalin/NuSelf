"""Tool-composition decorators for NuSelf.

Approval is a synchronous callable wrapper. Deferred approval does not retain
Python callables in process-global state.
"""
from .approval import approval_required

__all__ = ["approval_required"]
