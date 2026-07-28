"""Versioned immutable envelopes for internal runtime messages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Literal, cast
from uuid import uuid4

from nuself.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext, current_runtime_context

MessageKind = Literal["request", "event", "job", "audit", "notification"]
RUNTIME_SCHEMA_VERSION = 1
_MESSAGE_KINDS = frozenset(
    {"request", "event", "job", "audit", "notification"}
)
_ENVELOPE_FIELDS = frozenset(
    {
        "message_id",
        "schema_version",
        "kind",
        "name",
        "producer",
        "created_at",
        "context",
        "payload",
    }
)


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
        if self.kind not in _MESSAGE_KINDS:
            raise ValueError("runtime envelope kind is invalid")
        if (
            type(self.schema_version) is not int
            or self.schema_version != RUNTIME_SCHEMA_VERSION
        ):
            raise ValueError("runtime envelope schema version is unsupported")
        for field_name in ("message_id", "name", "producer", "created_at"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"runtime envelope {field_name} must be a non-blank string"
                )
        _parse_aware_iso(self.created_at)
        _require_runtime_context(self.context)
        _require_payload_mapping(self.payload)
        object.__setattr__(
            self,
            "payload",
            cast(Mapping[str, object], _freeze_json(self.payload)),
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

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
    ) -> RuntimeEnvelope:
        """Strictly decode one versioned detached envelope record."""

        record_fields = set(record)
        missing = sorted(_ENVELOPE_FIELDS - record_fields)
        unknown = sorted(record_fields - _ENVELOPE_FIELDS)
        if missing or unknown:
            raise ValueError(
                "runtime envelope fields are invalid "
                f"(missing={missing!r}, unknown={unknown!r})"
            )
        kind = record["kind"]
        if not isinstance(kind, str) or kind not in _MESSAGE_KINDS:
            raise ValueError("runtime envelope kind is invalid")
        schema_version = record["schema_version"]
        if type(schema_version) is not int:
            raise ValueError(
                "runtime envelope schema version must be an integer"
            )
        context = record["context"]
        if not isinstance(context, Mapping):
            raise TypeError("runtime envelope context must be a mapping")
        payload = record["payload"]
        if not isinstance(payload, Mapping):
            raise TypeError("runtime envelope payload must be a mapping")
        return cls(
            kind=cast(MessageKind, kind),
            name=_record_string(record, "name"),
            producer=_record_string(record, "producer"),
            message_id=_record_string(record, "message_id"),
            schema_version=schema_version,
            created_at=_record_string(record, "created_at"),
            context=RuntimeContext.from_record(
                cast(Mapping[str, object], context)
            ),
            payload=cast(Mapping[str, object], payload),
        )


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise TypeError("runtime payload floats must be finite")
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        frozen: dict[str, object] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("runtime payload mapping keys must be strings")
            frozen[key] = _freeze_json(item)
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


def _record_string(
    record: Mapping[str, object],
    field_name: str,
) -> str:
    value = record[field_name]
    if not isinstance(value, str):
        raise ValueError(
            f"runtime envelope {field_name} must be a string"
        )
    return value


def _require_runtime_context(value: object) -> RuntimeContext:
    if not isinstance(value, RuntimeContext):
        raise TypeError("runtime envelope context must be a RuntimeContext")
    return value


def _require_payload_mapping(
    value: object,
) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise TypeError("runtime envelope payload must be a mapping")
    return cast(Mapping[object, object], value)


def _parse_aware_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "runtime envelope created_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "runtime envelope created_at must include a timezone"
        )
    return parsed
