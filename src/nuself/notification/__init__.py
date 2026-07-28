"""Notification outbox and adapters for proactive agent surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from nuself.clock import utc_now, utc_now_iso
from nuself.config import runtime_paths
from nuself.runtime.observability import decode_observed_record
from nuself.storage import StorageBackend

OutboxStatus = Literal["pending", "sent", "failed", "dismissed"]


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

    def __post_init__(self) -> None:
        _parse_aware_iso(self.created_at, field_name="created_at")
        if self.sent_at is not None:
            _parse_aware_iso(self.sent_at, field_name="sent_at")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "attempts": self.attempts,
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
        )


class NotificationAdapter(Protocol):
    """Adapter that delivers one outbox entry to a notification channel."""

    def send(self, entry: OutboxEntry) -> bool:
        """Attempt to deliver the entry. Return True on success."""
        ...


class LogOnlyNotificationAdapter:
    """Write notification intents to a structured log file."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

    def send(self, entry: OutboxEntry) -> bool:
        from nuself.logs import write_log_event

        write_log_event(
            "outbox",
            "outbox_delivered",
            f"{entry.title}: {entry.body}",
            project_root=self._project_root,
            status=entry.status,
            metadata={
                "entry_id": entry.id,
                "idempotency_key": entry.idempotency_key,
                "deep_link": entry.deep_link,
                "attempts": entry.attempts,
            },
        )
        return True


class NotificationOutbox:
    """File-backed notification outbox under private/outbox/."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        from nuself.storage import auto_backend
        be = backend if backend is not None else auto_backend(project_root)
        self._col = be.collection("notification_outbox")
        self._project_root = runtime_paths(project_root).project_root

    def list(self, status: OutboxStatus | None = None) -> list[OutboxEntry]:
        entries: list[OutboxEntry] = []
        for wire in self._col.list():
            entry = decode_observed_record(
                wire,
                OutboxEntry.from_wire,
                component="outbox",
                collection="notification_outbox",
                project_root=self._project_root,
            )
            if entry is None:
                continue
            if status is None or entry.status == status:
                entries.append(entry)
        return entries

    def get(self, entry_id: str) -> OutboxEntry:
        wire = self._col.get(entry_id)
        if wire is None:
            raise OutboxEntryNotFound(entry_id)
        return OutboxEntry.from_wire(wire)

    def add(self, entry: OutboxEntry) -> OutboxEntry:
        # Single scan for the idempotency key (the exists-check and the lookup
        # were previously two separate full-collection scans per insert).
        existing = self._find_by_idempotency_key(entry.idempotency_key)
        if existing is not None:
            return existing
        self._col.put(entry.id, entry.to_wire())
        return entry

    def _write_entry(self, entry: OutboxEntry) -> None:
        self._col.put(entry.id, entry.to_wire())

    def mark_sent(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="sent",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=utc_now_iso(),
            attempts=entry.attempts + 1,
        )
        self._write_entry(updated)
        return updated

    def mark_failed(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="failed",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=entry.sent_at,
            attempts=entry.attempts + 1,
        )
        self._write_entry(updated)
        return updated

    def dismiss(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="dismissed",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=entry.sent_at,
            attempts=entry.attempts,
        )
        self._write_entry(updated)
        return updated

    def clear(self, status: OutboxStatus) -> int:
        removed = 0
        for entry in self.list(status=status):
            self._col.delete(entry.id)
            removed += 1
        return removed

    def clear_dismissed_older_than(self, days: int) -> int:
        if type(days) is not int or days < 0:
            raise ValueError("retention days must be a non-negative integer")
        removed = 0
        cutoff = utc_now().timestamp() - days * 86400
        for entry in self.list(status="dismissed"):
            created = _parse_aware_iso(
                entry.created_at,
                field_name="created_at",
            )
            if created.timestamp() < cutoff:
                self._col.delete(entry.id)
                removed += 1
        return removed

    def _find_by_idempotency_key(self, key: str) -> OutboxEntry | None:
        for entry in self.list():
            if entry.idempotency_key == key:
                return entry
        return None


class NotificationDeliveryLoop:
    """Polls the outbox and dispatches pending entries through adapters."""

    def __init__(
        self,
        project_root: Path | None = None,
        adapters: list[NotificationAdapter] | None = None,
    ) -> None:
        self._outbox = NotificationOutbox(project_root)
        self._adapters = adapters or [LogOnlyNotificationAdapter(project_root)]

    def run_once(self) -> int:
        """Deliver all pending entries. Return count delivered."""
        delivered = 0
        for entry in self._outbox.list(status="pending"):
            success = False
            for adapter in self._adapters:
                if adapter.send(entry):
                    success = True
                else:
                    success = False
                    break
            if success:
                self._outbox.mark_sent(entry.id)
                delivered += 1
            else:
                self._outbox.mark_failed(entry.id)
        # Clean up old dismissed entries so the outbox does not grow forever.
        self._outbox.clear_dismissed_older_than(days=7)
        return delivered


class OutboxEntryNotFound(ValueError):
    """Raised when an outbox entry does not exist."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"outbox entry not found: {entry_id}")


# --- small helpers ---


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
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


def _parse_aware_iso(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"field '{field_name}' must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"field '{field_name}' must include a timezone"
        )
    return parsed


def _expect_status(data: dict[str, object], field_name: str) -> OutboxStatus:
    value = _expect_str(data, field_name)
    if value not in {"pending", "sent", "failed", "dismissed"}:
        raise ValueError(f"unsupported outbox status: {value}")
    return cast(OutboxStatus, value)
