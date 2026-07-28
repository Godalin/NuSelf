from __future__ import annotations

from collections.abc import Mapping

import pytest

from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
    DuplicateAuditDefinitionError,
    UnknownAuditDefinitionError,
)


def _validate_id(metadata: Mapping[str, object]) -> None:
    if set(metadata) != {"id"} or not isinstance(metadata["id"], str):
        raise AuditSchemaError("id metadata is invalid")


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


def test_audit_definition_validates_exact_projection_contract() -> None:
    definition = AuditEventDefinition(
        "memory",
        "entry_failed",
        "error",
        "failed",
        error_policy="required",
        metadata_validator=_validate_id,
    )

    definition.validate(
        level="error",
        status="failed",
        error="failure",
        metadata={"id": "m1"},
    )

    with pytest.raises(AuditSchemaError, match="requires level"):
        definition.validate(
            level="warning",
            status="failed",
            error="failure",
            metadata={"id": "m1"},
        )
    with pytest.raises(AuditSchemaError, match="requires an error"):
        definition.validate(
            level="error",
            status="failed",
            error=None,
            metadata={"id": "m1"},
        )
    with pytest.raises(AuditSchemaError, match="id metadata"):
        definition.validate(
            level="error",
            status="failed",
            error="failure",
            metadata={},
        )
