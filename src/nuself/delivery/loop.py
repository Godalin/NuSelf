"""Delivery orchestration over independent Inbox and Delivery stores."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from nuself.delivery.adapters import DeliveryAdapter
from nuself.delivery.model import DeliveryRecord
from nuself.delivery.service import DeliveryService
from nuself.inbox.service import InboxService
from nuself.inbox.service import InboxItemNotFound
from nuself.runtime.context import use_runtime_context


class DeliveryLoop:
    def __init__(
        self,
        inbox: InboxService,
        store: DeliveryService,
        adapters: Sequence[DeliveryAdapter],
    ) -> None:
        self._inbox = inbox
        self._store = store
        self._adapters = _index(adapters)

    def run_once(self) -> int:
        delivered = 0
        for record in self._store.list(status="pending"):
            context = replace(record.context, source="daemon.worker.delivery")
            with use_runtime_context(context):
                if self.deliver(record.id).status == "sent":
                    delivered += 1
        return delivered

    def deliver(self, record_id: str) -> DeliveryRecord:
        with self._store.lock(record_id):
            record = self._store.get(record_id)
            if record.status != "pending":
                return record
            record = self._store.prepare(record.id, tuple(self._adapters))
            record = self._store.recover(record.id)
            try:
                item = self._inbox.get(record.item_id)
            except InboxItemNotFound:
                for adapter_id in record.required_adapters:
                    current = self._store.get(record.id)
                    if current.results[adapter_id].status == "pending":
                        self._store.begin(record.id, adapter_id)
                        self._store.finish_adapter(
                            record.id, adapter_id, success=False
                        )
                return self._store.finalize(record.id)
            for adapter_id in record.required_adapters:
                current = self._store.get(record.id)
                result = current.results[adapter_id]
                if result.status != "pending":
                    continue
                started = self._store.begin(record.id, adapter_id)
                attempt = started.results[adapter_id].attempts
                adapter = self._adapters.get(adapter_id)
                success = (
                    adapter.send(item, attempt=attempt)
                    if adapter is not None else False
                )
                self._store.finish_adapter(
                    record.id, adapter_id, success=success
                )
            return self._store.finalize(record.id)


def _index(adapters: Sequence[DeliveryAdapter]) -> Mapping[str, DeliveryAdapter]:
    result: dict[str, DeliveryAdapter] = {}
    for adapter in adapters:
        adapter_id = getattr(adapter, "delivery_id", None)
        if not isinstance(adapter_id, str) or not adapter_id:
            raise ValueError("delivery adapter ID must be a non-empty string")
        if adapter_id in result:
            raise ValueError(f"duplicate delivery adapter ID: {adapter_id}")
        result[adapter_id] = adapter
    return result
