"""Shared execution adapter for domain-owned direct audit catalogs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from nuself.logs import write_log_event
from nuself.runtime.audit.definition import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    UnknownAuditDefinitionError,
)
from nuself.runtime.audit.types import LogComponent
from nuself.runtime.log_event import LogEvent
from nuself.runtime.observability import (
    report_defined_failure,
    run_observed_best_effort,
    write_observed_log_event,
)


class AuditCatalog[EventT: str]:
    """Sealed runtime behavior for one domain-owned audit vocabulary."""

    def __init__(
        self,
        definitions: Sequence[AuditEventDefinition],
        messages: Mapping[EventT, str] | None = None,
    ) -> None:
        registry = AuditDefinitionRegistry()
        by_event: dict[str, list[AuditEventDefinition]] = {}
        for definition in definitions:
            registry.register(definition)
            by_event.setdefault(definition.event, []).append(definition)
        self._registry = registry.seal()
        self._definitions = MappingProxyType(
            {event: tuple(items) for event, items in by_event.items()}
        )
        self._messages = MappingProxyType(dict(messages or {}))

    @property
    def registry(self) -> AuditDefinitionRegistry:
        return self._registry

    def definition(
        self,
        event: EventT,
        *,
        component: LogComponent | None = None,
    ) -> AuditEventDefinition:
        if component is not None:
            return self._registry.resolve(component, event)
        try:
            definitions = self._definitions[event]
        except KeyError as exc:
            raise UnknownAuditDefinitionError(
                f"direct audit is not registered: {event!r}"
            ) from exc
        if len(definitions) != 1:
            raise AuditSchemaError(
                f"audit event {event!r} requires an explicit component"
            )
        return definitions[0]

    def _message(self, event: EventT, override: str | None) -> str:
        if override is not None:
            return override
        try:
            return self._messages[event]
        except KeyError as exc:
            raise AuditSchemaError(
                f"audit event {event!r} has no registered message"
            ) from exc

    def write(
        self,
        event: EventT,
        message: str | None = None,
        *,
        project_root: Path | None,
        error: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, object] | None = None,
        conversation_id: str | None = None,
        request_id: str | None = None,
        component: LogComponent | None = None,
    ) -> LogEvent | None:
        definition = self.definition(event, component=component)
        event_metadata = metadata or {}
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=error,
            duration_ms=duration_ms,
            metadata=event_metadata,
        )
        return write_observed_log_event(
            definition.component,
            definition.event,
            self._message(event, message),
            project_root=project_root,
            level=definition.level,
            status=definition.status,
            error=error,
            duration_ms=duration_ms,
            metadata=dict(event_metadata),
            conversation_id=conversation_id,
            request_id=request_id,
        )

    def write_strict(
        self,
        event: EventT,
        *,
        project_root: Path | None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
        component: LogComponent | None = None,
    ) -> LogEvent:
        definition = self.definition(event, component=component)
        event_metadata = metadata or {}
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=None,
            metadata=event_metadata,
        )
        return write_log_event(
            definition.component,
            definition.event,
            self._message(event, message),
            project_root=project_root,
            level=definition.level,
            status=definition.status,
            metadata=dict(event_metadata),
        )

    def failure(
        self,
        exc: BaseException,
        *,
        event: EventT,
        project_root: Path | None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
        component: LogComponent | None = None,
    ) -> None:
        report_defined_failure(
            exc,
            definition=self.definition(event, component=component),
            message=self._message(event, message),
            project_root=project_root,
            metadata=dict(metadata or {}),
        )

    def observe[T](
        self,
        operation: Callable[[], T],
        *,
        event: EventT,
        project_root: Path | None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
        errors: tuple[type[Exception], ...] = (Exception,),
        component: LogComponent | None = None,
    ) -> T | None:
        definition = self.definition(event, component=component)
        event_metadata = metadata or {}
        if definition.status is None:
            raise AuditSchemaError(
                f"{definition.component}/{definition.event} failure "
                "requires status"
            )
        definition.validate(
            level=definition.level,
            status=definition.status,
            error="caught failure",
            metadata=event_metadata,
        )
        return run_observed_best_effort(
            operation,
            component=definition.component,
            event=definition.event,
            message=self._message(event, message),
            project_root=project_root,
            metadata=dict(event_metadata),
            errors=errors,
            level=definition.level,
            status=definition.status,
        )
