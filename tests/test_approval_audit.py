import pytest

from nuself.decorators.approval_audit import (
    APPROVAL_AUDIT_REGISTRY,
    write_approval_decided,
    write_approval_prompted,
)
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.audit_types import LOG_COMPONENTS


def test_approval_registry_is_complete_and_sealed() -> None:
    assert len(APPROVAL_AUDIT_REGISTRY.definitions) == len(LOG_COMPONENTS) * 2
    with pytest.raises(AuditDefinitionRegistrySealedError):
        APPROVAL_AUDIT_REGISTRY.register(
            AuditEventDefinition(
                component="chat",
                event="approval_extra",
                level="info",
                status=None,
            )
        )


def test_prompt_contract_rejects_blank_schema_data() -> None:
    with pytest.raises(AuditSchemaError, match="tool"):
        write_approval_prompted("chat", tool=" ", summary="tool()")
    with pytest.raises(AuditSchemaError, match="summary"):
        write_approval_prompted("chat", tool="tool", summary="")


@pytest.mark.parametrize(
    ("approved", "approver", "input_kind"),
    [
        (True, None, "affirmative"),
        (True, "user", "declined"),
        (False, "user", "declined"),
        (False, None, "affirmative"),
    ],
)
def test_decision_contract_rejects_inconsistent_variants(
    approved: bool,
    approver: str | None,
    input_kind: str,
) -> None:
    with pytest.raises(AuditSchemaError):
        write_approval_decided(
            "chat",
            tool="tool",
            approved=approved,
            approver=approver,
            input_kind=input_kind,  # type: ignore[arg-type]
        )


def test_decision_contract_writes_fixed_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[tuple[str, str, object, object]] = []

    def capture(
        _component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> object:
        records.append(
            (
                event,
                message,
                kwargs.get("status"),
                kwargs.get("metadata"),
            )
        )
        return object()

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        capture,
    )

    write_approval_decided(
        "reasoning",
        tool="reason_propose",
        approved=False,
        approver=None,
        input_kind="eof",
    )

    assert records == [
        (
            "approval_decided",
            "Tool approval decided",
            "decided",
            {
                "tool": "reason_propose",
                "approved": False,
                "approver": None,
                "input_kind": "eof",
            },
        )
    ]
