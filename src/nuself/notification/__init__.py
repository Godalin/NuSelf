"""Notification outbox and adapters for proactive agent surface."""

from __future__ import annotations

import fcntl
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, cast

from nuself.clock import utc_now, utc_now_iso
from nuself.config import runtime_paths
from nuself.notification.audit import write_notification_audit
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    use_runtime_context,
)
from nuself.runtime.observability import decode_observed_record
from nuself.private_fs import (
    ensure_private_directory,
    ensure_private_file,
)
from nuself.storage import (
    StorageBackend,
    get_default_backend,
    validate_storage_key,
)

OutboxStatus = Literal["pending", "sent", "failed", "dismissed"]
TerminalOutboxStatus = Literal["sent", "failed", "dismissed"]
NotificationClearStatus = Literal[
    "sent",
    "failed",
    "dismissed",
    "all-terminal",
]
AdapterDeliveryStatus = Literal[
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
            _parse_aware_iso(self.sent_at, field_name="sent_at")
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


def empty_adapter_deliveries() -> dict[str, AdapterDelivery]:
    return {}


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
        default_factory=empty_adapter_deliveries
    )
    context: RuntimeContext = field(
        default_factory=current_runtime_context
    )

    def __post_init__(self) -> None:
        _parse_aware_iso(self.created_at, field_name="created_at")
        if self.sent_at is not None:
            _parse_aware_iso(self.sent_at, field_name="sent_at")
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


class NotificationAdapter(Protocol):
    """Adapter that delivers one outbox entry to a notification channel."""

    delivery_id: str

    def send(self, entry: OutboxEntry) -> bool:
        """Attempt to deliver the entry. Return True on success."""
        ...


class LogOnlyNotificationAdapter:
    """Write notification intents to a structured log file."""

    delivery_id = "log"

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

    def send(self, entry: OutboxEntry) -> bool:
        write_notification_audit(
            "outbox_delivered",
            project_root=self._project_root,
            metadata={
                "entry_id": entry.id,
                "attempt": entry.attempts,
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
        be = (
            backend
            if backend is not None
            else get_default_backend(project_root)
        )
        self._backend = be
        self._col = be.collection("notification_outbox")
        self._project_root = runtime_paths(project_root).project_root
        self._entry_lock_directory = (
            runtime_paths(project_root).authority_root
            / "notifications"
            / "locks"
        )

    def lock_entry(
        self,
        entry_id: str,
    ) -> AbstractContextManager[None]:
        """Serialize one entry across delivery, dismiss, and deletion."""
        validate_storage_key(entry_id)
        ensure_private_directory(self._entry_lock_directory)
        return _NotificationEntryLock(
            self._entry_lock_directory / f"{entry_id}.lock"
        )

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
        with self._backend.transaction():
            existing = self._find_by_idempotency_key(entry.idempotency_key)
            if existing is not None:
                return existing
            self._col.put(entry.id, entry.to_wire())
            return entry

    def _write_entry(self, entry: OutboxEntry) -> None:
        self._col.put(entry.id, entry.to_wire())

    def prepare_delivery(
        self,
        entry_id: str,
        adapter_ids: tuple[str, ...],
    ) -> OutboxEntry:
        _validate_adapter_ids(adapter_ids)
        with self._backend.transaction():
            entry = self.get(entry_id)
            if entry.required_adapters:
                return entry
            updated = replace(
                entry,
                required_adapters=adapter_ids,
                deliveries={
                    adapter_id: AdapterDelivery()
                    for adapter_id in adapter_ids
                },
            )
            self._write_entry(updated)
            return updated

    def record_adapter_result(
        self,
        entry_id: str,
        adapter_id: str,
        *,
        success: bool,
    ) -> OutboxEntry:
        if type(success) is not bool:
            raise TypeError("adapter delivery success must be a boolean")
        with self._backend.transaction():
            entry = self.get(entry_id)
            state = entry.deliveries.get(adapter_id)
            if state is None:
                raise ValueError(
                    f"adapter is not required for outbox entry: {adapter_id}"
                )
            if state.status != "delivering":
                return entry
            deliveries = dict(entry.deliveries)
            deliveries[adapter_id] = AdapterDelivery(
                status="sent" if success else "failed",
                attempts=state.attempts,
                sent_at=utc_now_iso() if success else None,
            )
            updated = replace(entry, deliveries=deliveries)
            self._write_entry(updated)
            return updated

    def begin_adapter_delivery(
        self,
        entry_id: str,
        adapter_id: str,
    ) -> OutboxEntry:
        with self._backend.transaction():
            entry = self.get(entry_id)
            state = entry.deliveries.get(adapter_id)
            if state is None:
                raise ValueError(
                    f"adapter is not required for outbox entry: {adapter_id}"
                )
            if state.status != "pending":
                return entry
            deliveries = dict(entry.deliveries)
            deliveries[adapter_id] = AdapterDelivery(
                status="delivering",
                attempts=state.attempts + 1,
            )
            updated = replace(entry, deliveries=deliveries)
            self._write_entry(updated)
            return updated

    def recover_interrupted_deliveries(
        self,
        entry_id: str,
    ) -> OutboxEntry:
        with self._backend.transaction():
            entry = self.get(entry_id)
            interrupted = tuple(
                adapter_id
                for adapter_id, state in entry.deliveries.items()
                if state.status == "delivering"
            )
            if not interrupted:
                return entry
            deliveries = dict(entry.deliveries)
            for adapter_id in interrupted:
                state = deliveries[adapter_id]
                deliveries[adapter_id] = AdapterDelivery(
                    status="uncertain",
                    attempts=state.attempts,
                )
            updated = replace(entry, deliveries=deliveries)
            self._write_entry(updated)
            return updated

    def finalize_delivery(self, entry_id: str) -> OutboxEntry:
        with self._backend.transaction():
            entry = self.get(entry_id)
            states = tuple(entry.deliveries.values())
            if not states or any(
                state.status in {"pending", "delivering"}
                for state in states
            ):
                status: OutboxStatus = "pending"
            elif all(state.status == "sent" for state in states):
                status = "sent"
            else:
                status = "failed"
            if status == entry.status:
                return entry
            updated = replace(
                entry,
                status=status,
                sent_at=utc_now_iso() if status == "sent" else entry.sent_at,
                attempts=entry.attempts + 1,
            )
            self._write_entry(updated)
            return updated

    def dismiss(self, entry_id: str) -> OutboxEntry:
        with self.lock_entry(entry_id):
            with self._backend.transaction():
                entry = self.get(entry_id)
                updated = replace(entry, status="dismissed")
                self._write_entry(updated)
                return updated

    def clear(self, selection: NotificationClearStatus) -> int:
        statuses: tuple[TerminalOutboxStatus, ...] = (
            ("sent", "failed", "dismissed")
            if selection == "all-terminal"
            else (selection,)
        )
        removed = 0
        for status in statuses:
            for entry in self.list(status=status):
                with self.lock_entry(entry.id):
                    try:
                        current = self.get(entry.id)
                    except OutboxEntryNotFound:
                        continue
                    if current.status == status:
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
                with self.lock_entry(entry.id):
                    try:
                        current = self.get(entry.id)
                    except OutboxEntryNotFound:
                        continue
                    if current.status == "dismissed":
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
        if adapters is None:
            from nuself.notification.composition import (
                build_notification_adapters,
            )

            adapters = build_notification_adapters(project_root)
        self._adapters = adapters

    def run_once(self) -> int:
        """Deliver all pending entries. Return count delivered."""
        _index_adapters(self._adapters)
        delivered = 0
        for entry in self._outbox.list(status="pending"):
            delivery_context = replace(
                entry.context,
                source="daemon.worker.notification_delivery",
            )
            with use_runtime_context(delivery_context):
                final = deliver_entry_once(
                    self._outbox,
                    entry.id,
                    self._adapters,
                )
                if final.status == "sent":
                    delivered += 1
        # Clean up old dismissed entries so the outbox does not grow forever.
        self._outbox.clear_dismissed_older_than(days=7)
        return delivered


def deliver_entry_once(
    outbox: NotificationOutbox,
    entry_id: str,
    adapters: list[NotificationAdapter],
) -> OutboxEntry:
    """Run or recover one frozen adapter plan without implicit retries."""
    indexed = _index_adapters(adapters)
    with outbox.lock_entry(entry_id):
        entry = outbox.get(entry_id)
        if entry.status != "pending":
            return entry
        outbox.prepare_delivery(entry_id, tuple(indexed))
        recovered = outbox.recover_interrupted_deliveries(entry_id)
        for adapter_id in recovered.required_adapters:
            current = outbox.get(entry_id)
            if current.deliveries[adapter_id].status != "pending":
                continue
            started = outbox.begin_adapter_delivery(
                entry_id,
                adapter_id,
            )
            adapter = indexed.get(adapter_id)
            success = adapter.send(started) if adapter is not None else False
            outbox.record_adapter_result(
                entry_id,
                adapter_id,
                success=success,
            )
        return outbox.finalize_delivery(entry_id)


class _NotificationEntryLock:
    """One stable blocking cross-process lock for an outbox entry."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = None

    def __enter__(self) -> None:
        ensure_private_file(self._path)
        self._file = self._path.open("ab")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


def _decode_context(data: dict[str, object]) -> RuntimeContext:
    if "context" not in data:
        return RuntimeContext()
    value = data["context"]
    if not isinstance(value, Mapping):
        raise TypeError("field 'context' must be an object")
    return RuntimeContext.from_record(
        cast(Mapping[str, object], value)
    )


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
    if type(value) is not int:
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


def _expect_adapter_delivery_status(
    data: dict[str, object],
    field_name: str,
) -> AdapterDeliveryStatus:
    value = _expect_str(data, field_name)
    if value not in {
        "pending",
        "delivering",
        "sent",
        "failed",
        "uncertain",
    }:
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


def _decode_deliveries(
    data: dict[str, object],
) -> dict[str, AdapterDelivery]:
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


def _validate_adapter_ids(adapter_ids: tuple[str, ...]) -> None:
    if (
        not adapter_ids
        or any(not adapter_id for adapter_id in adapter_ids)
        or len(set(adapter_ids)) != len(adapter_ids)
    ):
        raise ValueError(
            "notification adapter IDs must be non-empty and unique"
        )


def _index_adapters(
    adapters: list[NotificationAdapter],
) -> dict[str, NotificationAdapter]:
    indexed: dict[str, NotificationAdapter] = {}
    for adapter in adapters:
        adapter_id = getattr(adapter, "delivery_id", None)
        if not isinstance(adapter_id, str) or not adapter_id:
            raise ValueError(
                "notification adapter delivery_id must be a non-empty string"
            )
        if adapter_id in indexed:
            raise ValueError(
                f"duplicate notification adapter delivery_id: {adapter_id}"
            )
        indexed[adapter_id] = adapter
    _validate_adapter_ids(tuple(indexed))
    return indexed
