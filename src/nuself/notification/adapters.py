"""Notification delivery adapter contract and built-in log adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself.notification.audit import write_notification_audit
from nuself.notification.model import OutboxEntry


class NotificationAdapter(Protocol):
    """Adapter that delivers one outbox entry to a notification channel."""

    delivery_id: str

    def send(self, entry: OutboxEntry) -> bool:
        """Attempt to deliver the entry. Return True on success."""
        ...


class LogOnlyNotificationAdapter:
    """Write notification intents to a structured log file."""

    delivery_id = "log"

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

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
