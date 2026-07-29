"""Sealed definitions for non-persisting terminal warnings."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistryUnsealedError,
)
from nuself.runtime.diagnostics import (
    diagnostic_exception_message,
    emit_runtime_warning,
    redact_sensitive_text,
)

WarningMetadataValidator = Callable[[Mapping[str, object]], None]
_WARNING_IDENTITY_RE = re.compile(
    r"^[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)$"
)


class TerminalWarningSchemaError(ValueError):
    """A terminal warning producer violated its registered contract."""


class TerminalWarningRegistryUnsealedError(RuntimeError):
    """Warning rendering started before composition was sealed."""


def _accept_metadata(_metadata: Mapping[str, object]) -> None:
    return


@dataclass(frozen=True)
class TerminalWarningDefinition:
    """One terminal warning identity and canonical rendering contract."""

    event: str
    fields: tuple[str, ...]
    metadata_validator: WarningMetadataValidator = _accept_metadata
    suffix: str | None = None

    def __post_init__(self) -> None:
        if _WARNING_IDENTITY_RE.fullmatch(self.event) is None:
            raise ValueError("terminal warning event is invalid")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("terminal warning fields must be unique")
        for field in self.fields:
            if (
                not field
                or not field.isidentifier()
                or field.startswith("_")
            ):
                raise ValueError("terminal warning field is invalid")
        if not callable(self.metadata_validator):
            raise TypeError(
                "terminal warning metadata validator must be callable"
            )
        if self.suffix is not None and not self.suffix.strip():
            raise ValueError("terminal warning suffix must not be blank")

    def render(self, metadata: Mapping[str, object]) -> str:
        """Validate and render one credential-safe single-line warning."""

        actual = frozenset(metadata)
        expected = frozenset(self.fields)
        if actual != expected:
            raise TerminalWarningSchemaError(
                "terminal warning metadata fields differ "
                f"(missing={sorted(expected - actual)!r}, "
                f"extra={sorted(actual - expected)!r})"
            )
        self.metadata_validator(metadata)
        facts = " ".join(
            f"{field}={_render_value(metadata[field])}"
            for field in self.fields
        )
        message = f"{self.event}: {facts}" if facts else self.event
        if self.suffix is not None:
            message = f"{message}; {self.suffix}"
        return redact_sensitive_text(message)


class TerminalWarningRegistry:
    """Duplicate-safe warning definitions sealed after composition."""

    def __init__(self) -> None:
        self._registry = DefinitionRegistry[
            str,
            TerminalWarningDefinition,
        ](
            lambda definition: definition.event,
            namespace="terminal warning",
        )

    def register(
        self,
        definition: TerminalWarningDefinition,
    ) -> TerminalWarningRegistry:
        self._registry.register(definition)
        return self

    def resolve(self, event: str) -> TerminalWarningDefinition:
        try:
            return self._registry.resolve(event)
        except DefinitionRegistryUnsealedError as exc:
            raise TerminalWarningRegistryUnsealedError(
                "terminal warning registry must be sealed before runtime use"
            ) from exc

    def seal(self) -> TerminalWarningRegistry:
        self._registry.seal()
        return self

    @property
    def definitions(self) -> tuple[TerminalWarningDefinition, ...]:
        return self._registry.definitions


def emit_registered_terminal_warning(
    registry: TerminalWarningRegistry,
    event: str,
    metadata: Mapping[str, object],
    *,
    stacklevel: int,
) -> None:
    """Resolve, render, and emit without replacing a primary outcome."""

    try:
        message = registry.resolve(event).render(metadata)
    except Exception as exc:
        safe_event = redact_sensitive_text(event)
        message = (
            "runtime/terminal_warning_render_failed: "
            f"event={safe_event} "
            f"error={diagnostic_exception_message(exc)}"
        )
    emit_runtime_warning(message, stacklevel=stacklevel + 1)


def _render_value(value: object) -> str:
    if type(value) is int:
        return str(value)
    if not isinstance(value, str) or not value.strip():
        raise TerminalWarningSchemaError(
            "terminal warning values must be integers or non-blank strings"
        )
    return " ".join(value.split())
