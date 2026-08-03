"""Explicit Inbox composition helpers for tests."""

from pathlib import Path

from nuself.config.settings import RuntimePaths, runtime_paths
from nuself.inbox.service import InboxService
from nuself.storage.authority import auto_backend
from nuself.storage.contract import StorageBackend


def inbox_service(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
) -> InboxService:
    paths = (
        root_or_paths
        if isinstance(root_or_paths, RuntimePaths)
        else runtime_paths(root_or_paths)
    )
    return InboxService(paths, backend or auto_backend(paths.authority_root))
