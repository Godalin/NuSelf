"""Immutable Inbox items and strict wire codec."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast

from nuself.runtime.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext, current_runtime_context

type InboxStatus = Literal["pending", "read", "dismissed", "resolved"]
type InboxTerminalStatus = Literal["dismissed", "resolved"]
type InboxClearStatus = Literal["dismissed", "resolved", "all-terminal"]


@dataclass(frozen=True)
class InboxItem:
    """One concise reference to a matter requiring user attention."""

    id: str
    title: str
    body: str
    kind: str = "system"
    source_id: str = "system"
    status: InboxStatus = "pending"
    idempotency_key: str = ""
    deep_link: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    context: RuntimeContext = field(default_factory=current_runtime_context)

    def __post_init__(self) -> None:
        for name in ("id", "kind", "source_id", "title", "idempotency_key"):
            if not getattr(self, name):
                raise ValueError(f"Inbox field '{name}' must be non-empty")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "source_id": self.source_id,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context": self.context.to_record(),
        }
        if self.deep_link is not None:
            wire["deep_link"] = self.deep_link
        return wire

    @classmethod
    def from_wire(cls, wire: dict[str, object]) -> "InboxItem":
        context = wire.get("context", {})
        if not isinstance(context, Mapping):
            raise TypeError("field 'context' must be an object")
        status = _string(wire, "status")
        if status not in {"pending", "read", "dismissed", "resolved"}:
            raise ValueError(f"unsupported Inbox status: {status}")
        deep_link = wire.get("deep_link")
        if deep_link is not None and not isinstance(deep_link, str):
            raise ValueError("field 'deep_link' must be a string")
        return cls(
            id=_string(wire, "id"),
            kind=_string(wire, "kind"),
            source_id=_string(wire, "source_id"),
            title=_string(wire, "title"),
            body=_string(wire, "body"),
            status=cast(InboxStatus, status),
            idempotency_key=_string(wire, "idempotency_key"),
            deep_link=deep_link,
            created_at=_string(wire, "created_at"),
            updated_at=_string(wire, "updated_at"),
            context=RuntimeContext.from_record(cast(Mapping[str, object], context)),
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
