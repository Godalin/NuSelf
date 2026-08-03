"""Delivery adapter contract and built-in log adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself.delivery.audit import DELIVERY_AUDIT
from nuself.inbox.model import InboxItem


class DeliveryAdapter(Protocol):
    """Adapter that presents one Inbox item through an external channel."""

    delivery_id: str

    def send(self, entry: InboxItem, *, attempt: int) -> bool:
        """Attempt to deliver the item. Return True on success."""
        ...


class LogDeliveryAdapter:
    """Present Inbox items through the structured log."""

    delivery_id = "log"

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def send(self, entry: InboxItem, *, attempt: int) -> bool:
        DELIVERY_AUDIT.write_strict(
            "item_delivered",
            project_root=self._project_root,
            metadata={
                "entry_id": entry.id,
                "attempt": attempt,
            },
        )
        return True
