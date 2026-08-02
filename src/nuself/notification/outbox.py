"""Durable notification outbox storage and locking."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace

from nuself.clock import utc_now, utc_now_iso
from nuself.config import RuntimePaths
from nuself.notification.model import (
    AdapterDelivery,
    NotificationClearStatus,
    OutboxEntry,
    OutboxStatus,
    TerminalOutboxStatus,
    parse_aware_timestamp,
)
from nuself.runtime.observability import decode_observed_record
from nuself.private_fs import blocking_private_file_lock
from nuself.storage.contract import (
    StorageBackend,
    validate_storage_key,
)

class NotificationOutbox:
    """Persistent outbox in one explicitly selected authority."""

    def __init__(
        self,
        paths: RuntimePaths,
        backend: StorageBackend,
    ) -> None:
        self._backend = backend
        self._col = backend.collection("notification_outbox")
        self._project_root = paths.authority_root
        self._entry_lock_directory = (
            paths.authority_root / "notifications" / "locks"
        )

    def lock_entry(
        self,
        entry_id: str,
    ) -> AbstractContextManager[None]:
        """Serialize one entry across delivery, dismiss, and deletion."""
        validate_storage_key(entry_id)
        return blocking_private_file_lock(
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
            existing = next(
                (
                    candidate
                    for candidate in self.list()
                    if candidate.idempotency_key == entry.idempotency_key
                ),
                None,
            )
            if existing is not None:
                return existing
            self._col.put(entry.id, entry.to_wire())
            return entry

    def enqueue(
        self,
        *,
        entry_id: str,
        title: str,
        body: str,
        idempotency_key: str,
        deep_link: str | None = None,
    ) -> None:
        """Persist one pending notification intent."""
        self.add(
            OutboxEntry(
                id=entry_id,
                title=title,
                body=body,
                status="pending",
                idempotency_key=idempotency_key,
                deep_link=deep_link,
            )
        )

    def prepare_delivery(
        self,
        entry_id: str,
        adapter_ids: tuple[str, ...],
    ) -> OutboxEntry:
        validate_adapter_ids(adapter_ids)
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
            self._col.put(updated.id, updated.to_wire())
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
            self._col.put(updated.id, updated.to_wire())
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
            self._col.put(updated.id, updated.to_wire())
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
            self._col.put(updated.id, updated.to_wire())
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
            self._col.put(updated.id, updated.to_wire())
            return updated

    def dismiss(self, entry_id: str) -> OutboxEntry:
        with self.lock_entry(entry_id):
            with self._backend.transaction():
                entry = self.get(entry_id)
                updated = replace(entry, status="dismissed")
                self._col.put(updated.id, updated.to_wire())
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
            created = parse_aware_timestamp(
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

class OutboxEntryNotFound(ValueError):
    """Raised when an outbox entry does not exist."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"outbox entry not found: {entry_id}")


def validate_adapter_ids(adapter_ids: tuple[str, ...]) -> None:
    if (
        not adapter_ids
        or any(not adapter_id for adapter_id in adapter_ids)
        or len(set(adapter_ids)) != len(adapter_ids)
    ):
        raise ValueError(
            "notification adapter IDs must be non-empty and unique"
        )
