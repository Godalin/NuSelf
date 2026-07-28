"""Versioned immutable envelopes for internal runtime messages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast
from uuid import uuid4

from nuself.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext, current_runtime_context

MessageKind = Literal["request", "event", "job", "audit", "notification"]
RUNTIME_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuntimeEnvelope:
    """Transport-neutral identity, correlation, and payload for a message."""

    kind: MessageKind
    name: str
    producer: str
    message_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: int = RUNTIME_SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    context: RuntimeContext = field(default_factory=current_runtime_context)
    payload: Mapping[str, object] = field(default_factory=lambda: cast(dict[str, object], {}))

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SCHEMA_VERSION:
            raise ValueError("runtime envelope schema version is unsupported")
        for field_name in ("message_id", "name", "producer", "created_at"):
            if not getattr(self, field_name):
                raise ValueError(f"runtime envelope {field_name} is required")
        object.__setattr__(
            self,
            "payload",
            cast(Mapping[str, object], _freeze_json(dict(self.payload))),
        )

    def to_record(self) -> dict[str, object]:
        """Serialize the envelope without exposing mutable internal payloads."""

        return {
            "message_id": self.message_id,
            "schema_version": self.schema_version,
            "kind": self.kind,
            "name": self.name,
            "producer": self.producer,
            "created_at": self.created_at,
            "context": self.context.to_record(),
            "payload": _thaw_json(self.payload),
        }


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        frozen = {str(key): _freeze_json(item) for key, item in mapping.items()}
        return MappingProxyType(frozen)
    if isinstance(value, list | tuple):
        items = cast(list[object] | tuple[object, ...], value)
        return tuple(_freeze_json(item) for item in items)
    raise TypeError(f"runtime payload value is not JSON-safe: {type(value).__name__}")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _thaw_json(item) for key, item in mapping.items()}
    if isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
        return [_thaw_json(item) for item in items]
    return value
