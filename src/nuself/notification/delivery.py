"""Notification delivery orchestration over an injected outbox."""

from __future__ import annotations

from dataclasses import replace

from nuself.notification.adapters import NotificationAdapter
from nuself.notification.outbox import (
    NotificationOutbox,
    validate_adapter_ids,
)
from nuself.notification.model import OutboxEntry
from nuself.runtime.context import use_runtime_context


class NotificationDeliveryLoop:
    """Poll an injected outbox through one explicit adapter plan."""

    def __init__(
        self,
        outbox: NotificationOutbox,
        adapters: list[NotificationAdapter],
    ) -> None:
        self._outbox = outbox
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
            started = outbox.begin_adapter_delivery(entry_id, adapter_id)
            adapter = indexed.get(adapter_id)
            success = adapter.send(started) if adapter is not None else False
            outbox.record_adapter_result(
                entry_id,
                adapter_id,
                success=success,
            )
        return outbox.finalize_delivery(entry_id)


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
    validate_adapter_ids(tuple(indexed))
    return indexed
