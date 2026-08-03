"""Durable delivery plans and adapter results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal, cast

from nuself.runtime.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext

type DeliveryStatus = Literal["pending", "sent", "failed"]
type AdapterStatus = Literal["pending", "delivering", "sent", "failed", "uncertain"]


@dataclass(frozen=True)
class AdapterResult:
    status: AdapterStatus = "pending"
    attempts: int = 0
    sent_at: str | None = None

    def __post_init__(self) -> None:
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("adapter attempts must be a non-negative integer")
        if self.status == "sent" and self.sent_at is None:
            raise ValueError("sent adapter result requires sent_at")
        if self.status != "sent" and self.sent_at is not None:
            raise ValueError("only a sent adapter result may have sent_at")
        if self.sent_at is not None:
            _aware(self.sent_at, "sent_at")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {"status": self.status, "attempts": self.attempts}
        if self.sent_at is not None:
            wire["sent_at"] = self.sent_at
        return wire

    @classmethod
    def from_wire(cls, wire: dict[str, object]) -> "AdapterResult":
        status = _string(wire, "status")
        if status not in {"pending", "delivering", "sent", "failed", "uncertain"}:
            raise ValueError(f"unsupported adapter status: {status}")
        attempts = wire.get("attempts")
        if type(attempts) is not int or attempts < 0:
            raise ValueError("adapter attempts must be a non-negative integer")
        sent_at = wire.get("sent_at")
        if sent_at is not None and not isinstance(sent_at, str):
            raise ValueError("field 'sent_at' must be a string")
        return cls(cast(AdapterStatus, status), attempts, sent_at)


@dataclass(frozen=True)
class DeliveryRecord:
    id: str
    item_id: str
    status: DeliveryStatus = "pending"
    required_adapters: tuple[str, ...] = ()
    results: Mapping[str, AdapterResult] = field(
        default_factory=dict[str, AdapterResult]
    )
    created_at: str = field(default_factory=utc_now_iso)
    context: RuntimeContext = field(default_factory=RuntimeContext)

    def __post_init__(self) -> None:
        if not self.id or not self.item_id:
            raise ValueError("delivery id and item_id must be non-empty")
        _aware(self.created_at, "created_at")
        adapters = tuple(self.required_adapters)
        if any(not value for value in adapters) or len(set(adapters)) != len(adapters):
            raise ValueError("required adapter IDs must be non-empty and unique")
        results = dict(self.results)
        if set(results) != set(adapters):
            raise ValueError("adapter results must exactly match required adapters")
        object.__setattr__(self, "required_adapters", adapters)
        object.__setattr__(self, "results", MappingProxyType(results))

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "status": self.status,
            "required_adapters": list(self.required_adapters),
            "results": {key: self.results[key].to_wire() for key in self.required_adapters},
            "created_at": self.created_at,
            "context": self.context.to_record(),
        }

    @classmethod
    def from_wire(cls, wire: dict[str, object]) -> "DeliveryRecord":
        status = _string(wire, "status")
        if status not in {"pending", "sent", "failed"}:
            raise ValueError(f"unsupported delivery status: {status}")
        raw_adapters: object = wire.get("required_adapters", [])
        if not isinstance(raw_adapters, list) or any(
            not isinstance(x, str) for x in cast(list[object], raw_adapters)
        ):
            raise ValueError("required_adapters must be a string list")
        raw_results: object = wire.get("results", {})
        if not isinstance(raw_results, Mapping):
            raise ValueError("results must be an object")
        results: dict[str, AdapterResult] = {}
        for key, value in cast(Mapping[object, object], raw_results).items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError("results must map adapter IDs to objects")
            results[key] = AdapterResult.from_wire(cast(dict[str, object], value))
        raw_context = wire.get("context", {})
        if not isinstance(raw_context, Mapping):
            raise ValueError("context must be an object")
        return cls(
            id=_string(wire, "id"),
            item_id=_string(wire, "item_id"),
            status=cast(DeliveryStatus, status),
            required_adapters=tuple(cast(list[str], raw_adapters)),
            results=results,
            created_at=_string(wire, "created_at"),
            context=RuntimeContext.from_record(cast(Mapping[str, object], raw_context)),
        )


def _string(wire: dict[str, object], name: str) -> str:
    value = wire.get(name)
    if not isinstance(value, str):
        raise ValueError(f"field '{name}' must be a string")
    return value


def _aware(value: str, name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"field '{name}' must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"field '{name}' must include a timezone")
