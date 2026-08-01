"""Explicit authority composition helpers for notification tests."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths, runtime_paths
from nuself.notification.outbox import NotificationOutbox
from nuself.storage import StorageBackend
from tests.backend import owned_backend


def notification_outbox(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
) -> NotificationOutbox:
    paths = (
        root_or_paths
        if isinstance(root_or_paths, RuntimePaths)
        else runtime_paths(root_or_paths)
    )
    return NotificationOutbox(
        paths,
        backend or owned_backend(paths.project_root),
    )
