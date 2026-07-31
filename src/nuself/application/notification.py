"""Application-owned notification persistence composition."""

from __future__ import annotations

from nuself.config import RuntimePaths
from nuself.notification import NotificationOutbox
from nuself.storage import StorageBackend


def compose_notification_outbox(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> NotificationOutbox:
    """Build notification persistence from explicit authority resources."""

    return NotificationOutbox(paths, backend)
