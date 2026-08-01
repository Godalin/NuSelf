"""Notification delivery adapter contract and built-in log adapter."""

from __future__ import annotations

from typing import Protocol

from nuself.config import RuntimePaths
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

    def __init__(self, paths: RuntimePaths) -> None:
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
