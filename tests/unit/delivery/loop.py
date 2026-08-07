"""Independent external-delivery contracts."""

from pathlib import Path

from nuself.config.settings import runtime_paths
from nuself.delivery.loop import DeliveryLoop
from nuself.delivery.store import DeliveryStore
from nuself.delivery.service import DeliveryService
from nuself.inbox.model import InboxItem
from nuself.inbox.service import InboxService
from nuself.storage.authority import auto_backend


class _Adapter:
    delivery_id = "test"

    def __init__(self) -> None:
        self.items: list[str] = []

    def send(self, entry: InboxItem, *, attempt: int) -> bool:
        assert attempt == 1
        self.items.append(entry.id)
        return True


def _resources(root: Path) -> tuple[InboxService, DeliveryService]:
    backend = auto_backend(root)
    paths = runtime_paths(root)
    return (
        InboxService(paths, backend),
        DeliveryService(DeliveryStore(paths, backend)),
    )


def test_delivery_references_inbox_without_copying_content(tmp_path: Path) -> None:
    inbox, deliveries = _resources(tmp_path)
    item = inbox.add(InboxItem(
        id="item-1", kind="reflection", source_id="reflection-1",
        title="Title", body="Private body", idempotency_key="reflection-1",
    ))
    record = deliveries.request(item.id, context=item.context)

    wire = record.to_wire()
    assert wire["item_id"] == item.id
    assert "title" not in wire
    assert "body" not in wire


def test_successful_delivery_does_not_resolve_inbox_item(tmp_path: Path) -> None:
    inbox, deliveries = _resources(tmp_path)
    item = inbox.add(InboxItem(
        id="item-1", title="Title", body="Body", idempotency_key="item-1",
    ))
    record = deliveries.request(item.id, context=item.context)
    adapter = _Adapter()

    final = DeliveryLoop(inbox, deliveries, (adapter,)).deliver(record.id)

    assert final.status == "sent"
    assert adapter.items == [item.id]
    assert inbox.get(item.id).status == "pending"


def test_completed_delivery_is_not_replayed(tmp_path: Path) -> None:
    inbox, deliveries = _resources(tmp_path)
    item = inbox.add(InboxItem(
        id="item-1", title="Title", body="Body", idempotency_key="item-1",
    ))
    record = deliveries.request(item.id, context=item.context)
    adapter = _Adapter()
    loop = DeliveryLoop(inbox, deliveries, (adapter,))

    loop.deliver(record.id)
    loop.deliver(record.id)

    assert adapter.items == [item.id]


def test_deleted_inbox_item_fails_delivery_without_external_effect(
    tmp_path: Path,
) -> None:
    inbox, deliveries = _resources(tmp_path)
    item = inbox.add(InboxItem(
        id="item-1", title="Title", body="Body", status="resolved",
        idempotency_key="item-1",
    ))
    record = deliveries.request(item.id, context=item.context)
    inbox.clear("resolved")
    adapter = _Adapter()

    final = DeliveryLoop(inbox, deliveries, (adapter,)).deliver(record.id)

    assert final.status == "failed"
    assert adapter.items == []
