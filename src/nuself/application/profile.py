"""Application-owned composition for the profile domain."""

from __future__ import annotations

from nuself.config import RuntimePaths
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import StorageBackend


def compose_profile_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ProfileItemRepository:
    """Compose profile persistence from already-owned resources."""

    return ProfileItemRepository(paths, backend=backend)
