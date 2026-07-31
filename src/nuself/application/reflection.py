"""Application-owned composition for the reflection domain."""

from __future__ import annotations

from nuself.config import RuntimePaths
from nuself.reflection.repository import ReflectionRepository
from nuself.storage import StorageBackend


def compose_reflection_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ReflectionRepository:
    """Compose reflection persistence from already-owned resources."""

    return ReflectionRepository(paths, backend=backend)
