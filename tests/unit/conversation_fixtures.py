"""Explicit ConversationStore composition helper for tests."""

from __future__ import annotations

from pathlib import Path

from nuself.conversation import ConversationStore as _ConversationStore
from nuself.config import runtime_paths
from nuself.storage import StorageBackend, get_default_backend


class ConversationStore(_ConversationStore):
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
