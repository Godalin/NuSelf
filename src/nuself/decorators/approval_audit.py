"""Closed audit contracts for synchronous tool approval."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from nuself.logs import LogComponent, LogEvent
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.audit_types import LOG_COMPONENTS
from nuself.runtime.observability import write_observed_log_event

ApprovalAuditEvent = Literal["approval_prompted", "approval_decided"]
ApprovalInputKind = Literal["affirmative", "declined", "eof", "interrupt"]

_MESSAGES: dict[ApprovalAuditEvent, str] = {
    "approval_prompted": "Tool approval requested",
    "approval_decided": "Tool approval decided",
}


def _require_exact(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    actual = frozenset(metadata)
    if actual != expected:
        raise AuditSchemaError(
            "approval audit metadata fields differ "
            f"(missing={sorted(expected - actual)!r}, "
            f"extra={sorted(actual - expected)!r})"
        )


def _require_non_blank_string(
    metadata: Mapping[str, object],
    field: str,
) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value.strip():
        raise AuditSchemaError(
            f"approval audit metadata {field} must be a non-blank string"
        )
    return value


def _validate_prompted(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"tool", "summary"}))
    _require_non_blank_string(metadata, "tool")
    _require_non_blank_string(metadata, "summary")


def _validate_decided(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"tool", "approved", "approver", "input_kind"}),
    )
    _require_non_blank_string(metadata, "tool")
    approved = metadata["approved"]
    if type(approved) is not bool:
        raise AuditSchemaError(
            "approval audit metadata approved must be a boolean"
        )
    approver = metadata["approver"]
    input_kind = metadata["input_kind"]
    if input_kind not in {"affirmative", "declined", "eof", "interrupt"}:
        raise AuditSchemaError(
            "approval audit metadata input_kind is invalid"
        )
    if approved:
        if input_kind != "affirmative":
            raise AuditSchemaError(
                "approved decision requires affirmative input"
            )
        if not isinstance(approver, str) or not approver.strip():
            raise AuditSchemaError(
                "approved decision requires a non-blank approver"
            )
        return
    if input_kind == "affirmative":
        raise AuditSchemaError(
            "negative decision forbids affirmative input"
        )
    if approver is not None:
        raise AuditSchemaError(
            "negative decision requires a null approver"
        )


def _build_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    for component in LOG_COMPONENTS:
        registry.register(
            AuditEventDefinition(
                component=component,
                event="approval_prompted",
                level="info",
                status="pending",
                metadata_validator=_validate_prompted,
            )
        )
        registry.register(
            AuditEventDefinition(
                component=component,
                event="approval_decided",
                level="info",
                status="decided",
                metadata_validator=_validate_decided,
            )
        )
    return registry.seal()


APPROVAL_AUDIT_REGISTRY = _build_registry()


def _write_approval_audit(
    component: LogComponent,
    event: ApprovalAuditEvent,
    metadata: dict[str, object],
) -> LogEvent | None:
    definition = APPROVAL_AUDIT_REGISTRY.resolve(component, event)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=None,
        metadata=metadata,
    )
    return write_observed_log_event(
        component,
        event,
        _MESSAGES[event],
        level=definition.level,
        status=definition.status,
        metadata=metadata,
    )


def write_approval_prompted(
    component: LogComponent,
    *,
    tool: str,
    summary: str,
) -> LogEvent | None:
    """Record one validated approval request."""

    return _write_approval_audit(
        component,
        "approval_prompted",
        {"tool": tool, "summary": summary},
    )


def write_approval_decided(
    component: LogComponent,
    *,
    tool: str,
    approved: bool,
    approver: str | None,
    input_kind: ApprovalInputKind,
) -> LogEvent | None:
    """Record one validated terminal approval decision."""

    return _write_approval_audit(
        component,
        "approval_decided",
        {
            "tool": tool,
            "approved": approved,
            "approver": approver,
            "input_kind": input_kind,
        },
    )
