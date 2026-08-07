"""Inbox persistence and user-attention operations."""

from __future__ import annotations

from dataclasses import replace

from nuself.config.settings import RuntimePaths
from nuself.inbox.model import InboxClearStatus, InboxItem, InboxStatus
from nuself.runtime.clock import utc_now_iso
from nuself.runtime.observability import decode_observed_record
from nuself.storage.contract import StorageBackend


class InboxItemNotFound(KeyError):
    """Raised when one requested Inbox item does not exist."""


class InboxService:
    """Authoritative API for durable user-attention items."""

    def __init__(self, paths: RuntimePaths, backend: StorageBackend) -> None:
        self._backend = backend
        self._collection = backend.collection("inbox_items")
        self._project_root = paths.authority_root

    def list(self, status: InboxStatus | None = None) -> list[InboxItem]:
        items: list[InboxItem] = []
        for wire in self._collection.list():
            item = decode_observed_record(
                wire,
                InboxItem.from_wire,
                component="inbox",
                collection="inbox_items",
                project_root=self._project_root,
            )
            if item is not None and (status is None or item.status == status):
                items.append(item)
        return items

    def get(self, item_id: str) -> InboxItem:
        wire = self._collection.get(item_id)
        if wire is None:
            raise InboxItemNotFound(item_id)
        return InboxItem.from_wire(wire)

    def add(self, item: InboxItem) -> InboxItem:
        with self._backend.transaction():
            existing = next(
                (candidate for candidate in self.list()
                 if candidate.idempotency_key == item.idempotency_key),
                None,
            )
            if existing is not None:
                return existing
            self._collection.put(item.id, item.to_wire())
        return item

    def mark_read(self, item_id: str) -> InboxItem:
        return self._transition(item_id, "read")

    def dismiss(self, item_id: str) -> InboxItem:
        return self._transition(item_id, "dismissed")

    def resolve(self, item_id: str) -> InboxItem:
        return self._transition(item_id, "resolved")

    def clear(self, status: InboxClearStatus = "all-terminal") -> int:
        selected = {"dismissed", "resolved"} if status == "all-terminal" else {status}
        removed = 0
        with self._backend.transaction():
            for item in self.list():
                if item.status in selected:
                    self._collection.delete(item.id)
                    removed += 1
        return removed

    def _transition(self, item_id: str, status: InboxStatus) -> InboxItem:
        with self._backend.transaction():
            item = self.get(item_id)
            updated = replace(item, status=status, updated_at=utc_now_iso())
            self._collection.put(item.id, updated.to_wire())
            return updated
