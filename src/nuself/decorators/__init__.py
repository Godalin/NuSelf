"""Simpler decorators package for NuSelf.

This module provides decorator primitives for tool composition:
`audit_log` and `approval_required`, plus `ApprovalManager` for runtime
management of pending approvals.
"""
from .approval import ApprovalManager, approval_required
from .audit import audit_log

__all__ = ["ApprovalManager", "approval_required", "audit_log"]
