from __future__ import annotations

from collections.abc import Mapping

import pytest

from nuself.runtime.audit.definition import (
    AuditDefinitionRegistry,
    AuditDefinitionRegistrySealedError,
    AuditDefinitionRegistryUnsealedError,
    AuditEventDefinition,
    AuditSchemaError,
    DuplicateAuditDefinitionError,
    UnknownAuditDefinitionError,
    require_exact_metadata,
)


def _validate_id(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(metadata, frozenset({"id"}))
    if not isinstance(metadata["id"], str):
        raise AuditSchemaError("id metadata is invalid")


def test_exact_metadata_validation_reports_missing_and_extra_fields() -> None:
    with pytest.raises(
        AuditSchemaError,
        match=r"example fields differ .*missing=\['id'\].*extra=\['other'\]",
    ):
        require_exact_metadata(
            {"other": 1},
            frozenset({"id"}),
            context="example",
        )


def test_audit_definition_registry_is_duplicate_safe_and_sealable() -> None:
    definition = AuditEventDefinition(
        "memory",
        "entry_created",
        "info",
        "created",
        metadata_validator=_validate_id,
    )
    registry = AuditDefinitionRegistry().register(definition)

    with pytest.raises(DuplicateAuditDefinitionError):
        registry.register(definition)

    registry.seal()
    assert registry.resolve("memory", "entry_created") is definition
    assert registry.definitions == (definition,)
    with pytest.raises(AuditDefinitionRegistrySealedError):
        registry.register(
            AuditEventDefinition(
                "memory",
                "entry_archived",
                "info",
                "archived",
            )
        )


def test_audit_definition_registry_rejects_unknown_identity() -> None:
    registry = AuditDefinitionRegistry().seal()

    with pytest.raises(UnknownAuditDefinitionError):
        registry.resolve("memory", "entry_created")


def test_audit_definition_registry_rejects_lookup_before_seal() -> None:
    registry = AuditDefinitionRegistry().register(
        AuditEventDefinition(
            "memory",
            "entry_created",
            "info",
            "created",
        )
    )

    with pytest.raises(AuditDefinitionRegistryUnsealedError):
        registry.resolve("memory", "entry_created")


def test_audit_definition_validates_exact_projection_contract() -> None:
    definition = AuditEventDefinition(
        "memory",
        "entry_failed",
        "error",
        "failed",
        error_policy="required",
        duration_policy="required",
        metadata_validator=_validate_id,
    )

    definition.validate(
        level="error",
        status="failed",
        error="failure",
        metadata={"id": "m1"},
        duration_ms=12,
    )

    with pytest.raises(AuditSchemaError, match="requires level"):
        definition.validate(
            level="warning",
            status="failed",
            error="failure",
            metadata={"id": "m1"},
            duration_ms=12,
        )
    with pytest.raises(AuditSchemaError, match="requires an error"):
        definition.validate(
            level="error",
            status="failed",
            error=None,
            metadata={"id": "m1"},
            duration_ms=12,
        )
    with pytest.raises(AuditSchemaError, match="missing=\\['id'\\]"):
        definition.validate(
            level="error",
            status="failed",
            error="failure",
            metadata={},
            duration_ms=12,
        )

    with pytest.raises(AuditSchemaError, match="requires a duration"):
        definition.validate(
            level="error",
            status="failed",
            error="failure",
            metadata={"id": "m1"},
        )


def test_audit_definition_accepts_absent_status_contract() -> None:
    definition = AuditEventDefinition(
        "memory",
        "entry_seen",
        "info",
        None,
    )

    definition.validate(
        level="info",
        status=None,
        error=None,
        metadata={},
    )

    with pytest.raises(AuditSchemaError, match="forbids a duration"):
        definition.validate(
            level="info",
            status=None,
            error=None,
            duration_ms=1,
            metadata={},
        )
