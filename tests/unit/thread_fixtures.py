"""Explicit ThreadStore composition helper for tests."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat.thread import ThreadStore as _ThreadStore
from nuself.config import runtime_paths
from nuself.storage import StorageBackend, get_default_backend


class ThreadStore(_ThreadStore):
    """Test convenience wrapper with an isolated authority per project root."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        super().__init__(
            runtime_paths(project_root),
            backend=backend or get_default_backend(project_root),
        )
