"""Terminal warning contracts emitted by the logging infrastructure."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from nuself.runtime.audit.types import LOG_COMPONENTS
from nuself.runtime.warning_definitions import (
    TerminalWarningDefinition,
    TerminalWarningRegistry,
    TerminalWarningSchemaError,
)


def _require_component(
    metadata: Mapping[str, object],
    field: str = "component",
) -> None:
    if metadata[field] not in LOG_COMPONENTS:
        raise TerminalWarningSchemaError(
            f"logging terminal warning {field} is invalid"
        )


def _require_string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value.strip():
        raise TerminalWarningSchemaError(
            f"logging terminal warning {field} must be non-blank"
        )
    return value


def _require_count(metadata: Mapping[str, object]) -> None:
    count = metadata["count"]
    if type(count) is not int or count < 1:
        raise TerminalWarningSchemaError(
            "logging terminal warning count must be positive"
        )


def _validate_lock_cleanup(metadata: Mapping[str, object]) -> None:
    _require_component(metadata)
    if metadata["operation"] not in {"unlock", "close"}:
        raise TerminalWarningSchemaError(
            "logging terminal warning operation is invalid"
        )
    _require_string(metadata, "error_type")


def _validate_component_error(metadata: Mapping[str, object]) -> None:
    _require_component(metadata)
    _require_string(metadata, "error_type")


def _validate_observer(metadata: Mapping[str, object]) -> None:
    _require_string(metadata, "observer_error")
    _require_string(metadata, "log_error")


def _validate_corruption(metadata: Mapping[str, object]) -> None:
    _require_component(metadata)
    filename = _require_string(metadata, "file")
    if Path(filename).name != filename:
        raise TerminalWarningSchemaError(
            "logging terminal warning file must be a basename"
        )
    _require_count(metadata)
    _require_string(metadata, "first_error")


def _validate_identity(metadata: Mapping[str, object]) -> None:
    _require_count(metadata)
    _require_component(metadata, "first_component")
    _require_string(metadata, "first_event")


def build_log_terminal_warning_registry() -> TerminalWarningRegistry:
    """Build the sealed warning schema registry used by ``nuself.logs``."""

    definitions = (
        TerminalWarningDefinition(
            "logs/lock_cleanup_failed",
            ("component", "operation", "error_type"),
            _validate_lock_cleanup,
        ),
        TerminalWarningDefinition(
            "logs/append_rollback_failed",
            ("component", "error_type"),
            _validate_component_error,
        ),
        TerminalWarningDefinition(
            "logs/rotation_failed",
            ("component", "error_type"),
            _validate_component_error,
            suffix="continuing without guaranteed retention bounds",
        ),
        TerminalWarningDefinition(
            "daemon/log_observer_failed",
            ("observer_error", "log_error"),
            _validate_observer,
        ),
        TerminalWarningDefinition(
            "logs/corrupt_records_skipped",
            ("component", "file", "count", "first_error"),
            _validate_corruption,
        ),
        TerminalWarningDefinition(
            "logs/event_identity_conflict",
            ("count", "first_component", "first_event"),
            _validate_identity,
        ),
    )
    registry = TerminalWarningRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


LOG_TERMINAL_WARNING_REGISTRY = build_log_terminal_warning_registry()
