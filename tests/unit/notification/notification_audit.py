from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.notification import audit
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)

_CANONICAL: tuple[tuple[str, dict[str, object]], ...] = (
    ("outbox_delivered", {"entry_id": "entry-1", "attempt": 0}),
    ("email_dry_run", {"entry_id": "entry-1", "attempt": 0}),
    ("email_no_config", {"entry_id": "entry-1", "attempt": 0}),
    ("email_failed", {"entry_id": "entry-1", "attempt": 1}),
    ("email_config_invalid", {"record": "email.toml"}),
    ("macos_dry_run", {"entry_id": "entry-1", "attempt": 0}),
    ("macos_unavailable", {"entry_id": "entry-1", "attempt": 0}),
    ("macos_failed", {"entry_id": "entry-1", "attempt": 1}),
)


def test_notification_registry_owns_complete_taxonomy() -> None:
    assert {
        definition.event
        for definition in audit.NOTIFICATION_AUDIT_REGISTRY.definitions
    } == {event for event, _ in _CANONICAL}


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_notification_definitions_accept_canonical_payloads(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.NOTIFICATION_AUDIT_REGISTRY.resolve("outbox", event)

    definition.validate(
        level=definition.level,
        status=definition.status,
        error=(
            "caught failure"
            if definition.error_policy == "required"
            else None
        ),
        metadata=metadata,
    )


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_notification_definitions_reject_private_or_unknown_metadata(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.NOTIFICATION_AUDIT_REGISTRY.resolve("outbox", event)

    with pytest.raises(AuditSchemaError, match="metadata"):
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=(
                "caught failure"
                if definition.error_policy == "required"
                else None
            ),
            metadata={**metadata, "body": "private notification"},
        )


def test_notification_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_log_event", unexpected_sink)

    with pytest.raises(UnknownAuditDefinitionError):
        audit.write_notification_audit(
            cast(audit.NotificationSuccessEvent, "outbox_deliverd"),
            project_root=tmp_path,
            metadata={"entry_id": "entry-1", "attempt": 0},
        )

    assert sink_calls == 0


def test_notification_audit_rejects_sensitive_metadata_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_log_event", unexpected_sink)

    with pytest.raises(AuditSchemaError, match="metadata"):
        audit.write_notification_audit(
            "outbox_delivered",
            project_root=tmp_path,
            metadata={
                "entry_id": "entry-1",
                "attempt": 0,
                "idempotency_key": "private-key",
            },
        )

    assert sink_calls == 0
