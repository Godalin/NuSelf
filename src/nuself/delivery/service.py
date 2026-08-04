"""Delivery user-intent and workflow service boundary."""

from __future__ import annotations

from contextlib import AbstractContextManager

from nuself.delivery.model import DeliveryRecord, DeliveryStatus
from nuself.delivery.store import DeliveryStore
from nuself.runtime.context import RuntimeContext


class DeliveryService:
    """Create, inspect, and advance durable delivery attempts."""

    def __init__(self, store: DeliveryStore) -> None:
        self._store = store

    def request(
        self,
        item_id: str,
        *,
        context: RuntimeContext,
    ) -> DeliveryRecord:
        return self._store.request(item_id, context=context)

    def list(self, status: DeliveryStatus | None = None) -> list[DeliveryRecord]:
        return self._store.list(status)

    def get(self, record_id: str) -> DeliveryRecord:
        return self._store.get(record_id)

    def lock(self, record_id: str) -> AbstractContextManager[None]:
        return self._store.lock(record_id)

    def prepare(
        self,
        record_id: str,
        adapters: tuple[str, ...],
    ) -> DeliveryRecord:
        return self._store.prepare(record_id, adapters)

    def recover(self, record_id: str) -> DeliveryRecord:
        return self._store.recover(record_id)

    def begin(self, record_id: str, adapter: str) -> DeliveryRecord:
        return self._store.begin(record_id, adapter)

    def finish_adapter(
        self,
        record_id: str,
        adapter: str,
        *,
        success: bool,
    ) -> DeliveryRecord:
        return self._store.finish_adapter(
            record_id,
            adapter,
            success=success,
        )

    def finalize(self, record_id: str) -> DeliveryRecord:
        return self._store.finalize(record_id)
