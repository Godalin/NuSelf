"""Immutable notification records and strict wire codecs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal, cast

from nuself.runtime.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext, current_runtime_context

type OutboxStatus = Literal["pending", "sent", "failed", "dismissed"]
type TerminalOutboxStatus = Literal["sent", "failed", "dismissed"]
type NotificationClearStatus = Literal[
    "sent",
    "failed",
    "dismissed",
    "all-terminal",
]
type AdapterDeliveryStatus = Literal[
    "pending",
    "delivering",
    "sent",
    "failed",
    "uncertain",
]


@dataclass(frozen=True)
class AdapterDelivery:
    """Durable delivery state for one stable notification adapter."""

    status: AdapterDeliveryStatus = "pending"
    attempts: int = 0
    sent_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            "pending",
            "delivering",
            "sent",
            "failed",
            "uncertain",
        }:
            raise ValueError(f"unsupported adapter delivery status: {self.status}")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("adapter delivery attempts must be a non-negative integer")
        if self.sent_at is not None:
            parse_aware_timestamp(self.sent_at, field_name="sent_at")
        if self.status == "sent" and self.sent_at is None:
            raise ValueError("sent adapter delivery requires sent_at")
        if self.status != "sent" and self.sent_at is not None:
            raise ValueError("non-sent adapter delivery must not define sent_at")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "status": self.status,
            "attempts": self.attempts,
        }
        if self.sent_at is not None:
            wire["sent_at"] = self.sent_at
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "AdapterDelivery":
        return cls(
            status=_expect_adapter_delivery_status(data, "status"),
            attempts=_expect_int(data, "attempts"),
            sent_at=_optional_timestamp(data, "sent_at"),
        )


@dataclass(frozen=True)
class OutboxEntry:
    """One notification intent in the outbox."""

    id: str
    title: str
    body: str
    status: OutboxStatus
    idempotency_key: str
    deep_link: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    sent_at: str | None = None
    attempts: int = 0
    required_adapters: tuple[str, ...] = ()
    deliveries: Mapping[str, AdapterDelivery] = field(
        default_factory=dict[str, AdapterDelivery]
    )
    context: RuntimeContext = field(default_factory=current_runtime_context)

    def __post_init__(self) -> None:
        parse_aware_timestamp(self.created_at, field_name="created_at")
        if self.sent_at is not None:
            parse_aware_timestamp(self.sent_at, field_name="sent_at")
        required_adapters = tuple(self.required_adapters)
        if (
            any(not adapter_id for adapter_id in required_adapters)
            or len(set(required_adapters)) != len(required_adapters)
        ):
            raise ValueError("required adapter IDs must be non-empty and unique")
        deliveries: dict[str, AdapterDelivery] = dict(self.deliveries)
        if set(deliveries) != set(required_adapters):
            raise ValueError("adapter deliveries must exactly match required adapters")
        object.__setattr__(self, "required_adapters", required_adapters)
        object.__setattr__(self, "deliveries", MappingProxyType(deliveries))

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "context": self.context.to_record(),
        }
        if self.required_adapters:
            wire["required_adapters"] = list(self.required_adapters)
            wire["deliveries"] = {
                adapter_id: self.deliveries[adapter_id].to_wire()
                for adapter_id in self.required_adapters
            }
        if self.deep_link is not None:
            wire["deep_link"] = self.deep_link
        if self.sent_at is not None:
            wire["sent_at"] = self.sent_at
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "OutboxEntry":
        return cls(
            id=_expect_str(data, "id"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            status=_expect_status(data, "status"),
            idempotency_key=_expect_str(data, "idempotency_key"),
            deep_link=_optional_str(data, "deep_link"),
            created_at=_expect_str(data, "created_at"),
            sent_at=_optional_timestamp(data, "sent_at"),
            attempts=_expect_int(data, "attempts"),
            required_adapters=_decode_required_adapters(data),
            deliveries=_decode_deliveries(data),
            context=_decode_context(data),
        )


def parse_aware_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"field '{field_name}' must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"field '{field_name}' must include a timezone")
    return parsed


def _decode_context(data: dict[str, object]) -> RuntimeContext:
    if "context" not in data:
        return RuntimeContext()
    value = data["context"]
    if not isinstance(value, Mapping):
        raise TypeError("field 'context' must be an object")
    return RuntimeContext.from_record(cast(Mapping[str, object], value))


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    return value if isinstance(value, str) else None


def _optional_timestamp(
    data: dict[str, object],
    field_name: str,
) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_int(data: dict[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if type(value) is not int:
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


def _expect_status(data: dict[str, object], field_name: str) -> OutboxStatus:
    value = _expect_str(data, field_name)
    if value not in {"pending", "sent", "failed", "dismissed"}:
        raise ValueError(f"unsupported outbox status: {value}")
    return cast(OutboxStatus, value)


def _expect_adapter_delivery_status(
    data: dict[str, object],
    field_name: str,
) -> AdapterDeliveryStatus:
    value = _expect_str(data, field_name)
    if value not in {"pending", "delivering", "sent", "failed", "uncertain"}:
        raise ValueError(f"unsupported adapter delivery status: {value}")
    return cast(AdapterDeliveryStatus, value)


def _decode_required_adapters(data: dict[str, object]) -> tuple[str, ...]:
    value = data.get("required_adapters")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("field 'required_adapters' must be a string list")
    raw_ids = cast(list[object], value)
    if any(not isinstance(adapter_id, str) for adapter_id in raw_ids):
        raise ValueError("field 'required_adapters' must be a string list")
    return tuple(cast(list[str], raw_ids))


def _decode_deliveries(data: dict[str, object]) -> dict[str, AdapterDelivery]:
    value = data.get("deliveries")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("field 'deliveries' must be an object")
    result: dict[str, AdapterDelivery] = {}
    mapping = cast(Mapping[object, object], value)
    for adapter_id, raw_state in mapping.items():
        if not isinstance(adapter_id, str) or not isinstance(raw_state, dict):
            raise ValueError(
                "field 'deliveries' must map adapter IDs to objects"
            )
        result[adapter_id] = AdapterDelivery.from_wire(
            cast(dict[str, object], raw_state)
        )
    return result
