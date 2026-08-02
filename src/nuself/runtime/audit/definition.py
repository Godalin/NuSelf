"""Closed domain contracts for direct persisted audit events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from nuself.runtime.audit.types import LOG_COMPONENTS, LogComponent, LogLevel
from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistrySealedError,
    DefinitionRegistryUnsealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)
from nuself.runtime.identities import require_audit_event_name

type AuditErrorPolicy = Literal["forbidden", "required"]
type AuditDurationPolicy = Literal["forbidden", "required", "optional"]
type AuditMetadataValidator = Callable[[Mapping[str, object]], None]


class AuditSchemaError(ValueError):
    """A direct audit producer violated its registered contract."""


class DuplicateAuditDefinitionError(ValueError):
    """A component/event pair was registered twice."""


class AuditDefinitionRegistrySealedError(RuntimeError):
    """A sealed audit definition registry was mutated."""


class AuditDefinitionRegistryUnsealedError(RuntimeError):
    """Audit lookup started before composition was sealed."""


class UnknownAuditDefinitionError(LookupError):
    """A direct audit event has no owning definition."""


def require_exact_metadata(
    metadata: Mapping[str, object],
    expected: frozenset[str],
    *,
    context: str = "audit metadata",
) -> None:
    """Require one exact metadata field set before value validation."""

    actual = frozenset(metadata)
    if actual != expected:
        raise AuditSchemaError(
            f"{context} fields differ "
            f"(missing={sorted(expected - actual)!r}, "
            f"extra={sorted(actual - expected)!r})"
        )


def _validate_no_metadata(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(metadata, frozenset())


@dataclass(frozen=True)
class AuditEventDefinition:
    """One direct audit identity and its exact projection contract."""

    component: LogComponent
    event: str
    level: LogLevel
    status: str | None
    error_policy: AuditErrorPolicy = "forbidden"
    duration_policy: AuditDurationPolicy = "forbidden"
    metadata_validator: AuditMetadataValidator = _validate_no_metadata

    def __post_init__(self) -> None:
        if self.component not in LOG_COMPONENTS:
            raise ValueError("audit definition component is invalid")
        require_audit_event_name(self.event)
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError("audit definition level is invalid")
        if self.status is not None and not self.status:
            raise ValueError("audit definition status must not be empty")
        if self.error_policy not in {"forbidden", "required"}:
            raise ValueError("audit definition error policy is invalid")
        if self.duration_policy not in {"forbidden", "required", "optional"}:
            raise ValueError("audit definition duration policy is invalid")
        if not callable(self.metadata_validator):
            raise TypeError("audit metadata validator must be callable")

    def validate(
        self,
        *,
        level: LogLevel,
        status: str | None,
        error: str | None,
        metadata: Mapping[str, object],
        duration_ms: int | None = None,
    ) -> None:
        if level != self.level:
            raise AuditSchemaError(
                f"{self.component}/{self.event} requires level {self.level!r}"
            )
        if status != self.status:
            raise AuditSchemaError(
                f"{self.component}/{self.event} requires status {self.status!r}"
            )
        if self.error_policy == "required":
            if not isinstance(error, str) or not error:
                raise AuditSchemaError(
                    f"{self.component}/{self.event} requires an error"
                )
        elif error is not None:
            raise AuditSchemaError(
                f"{self.component}/{self.event} forbids an error"
            )
        if duration_ms is not None and (
            type(duration_ms) is not int or duration_ms < 0
        ):
            raise AuditSchemaError(
                f"{self.component}/{self.event} duration is invalid"
            )
        if self.duration_policy == "required" and duration_ms is None:
            raise AuditSchemaError(
                f"{self.component}/{self.event} requires a duration"
            )
        if self.duration_policy == "forbidden" and duration_ms is not None:
            raise AuditSchemaError(
                f"{self.component}/{self.event} forbids a duration"
            )
        self.metadata_validator(metadata)


class AuditDefinitionRegistry:
    """Duplicate-safe domain audit registry sealed after composition."""

    def __init__(self) -> None:
        self._registry = DefinitionRegistry[
            tuple[LogComponent, str],
            AuditEventDefinition,
        ](
            lambda definition: (definition.component, definition.event),
            namespace="direct audit",
        )

    def register(
        self,
        definition: AuditEventDefinition,
    ) -> AuditDefinitionRegistry:
        try:
            self._registry.register(definition)
        except DefinitionRegistrySealedError as exc:
            raise AuditDefinitionRegistrySealedError(
                "audit definition registry is sealed"
            ) from exc
        except DuplicateDefinitionError as exc:
            raise DuplicateAuditDefinitionError(
                f"audit definition already registered: {exc.key!r}"
            ) from exc
        return self

    def resolve(
        self,
        component: LogComponent,
        event: str,
    ) -> AuditEventDefinition:
        try:
            return self._registry.resolve((component, event))
        except DefinitionRegistryUnsealedError as exc:
            raise AuditDefinitionRegistryUnsealedError(
                "audit definition registry must be sealed before runtime use"
            ) from exc
        except UnknownDefinitionError as exc:
            raise UnknownAuditDefinitionError(
                f"direct audit is not registered: {(component, event)!r}"
            ) from exc

    def seal(self) -> AuditDefinitionRegistry:
        self._registry.seal()
        return self

    @property
    def definitions(self) -> tuple[AuditEventDefinition, ...]:
        return self._registry.definitions
