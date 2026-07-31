"""Application-owned composition for the reason domain."""

from __future__ import annotations

from nuself.config import RuntimePaths
from nuself.reason.repository import ReasonRepository
from nuself.storage import StorageBackend


def compose_reason_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ReasonRepository:
    """Compose reason persistence from already-owned resources."""

    return ReasonRepository(paths, backend=backend)
