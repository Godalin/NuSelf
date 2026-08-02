"""Narrow cross-domain contracts for profile persistence."""

from __future__ import annotations

from typing import Protocol

from nuself.memory.model import MemoryCandidate
from nuself.profile.model import ProfileItem


class ProfileRepositoryPort(Protocol):
    """Capabilities consumed outside profile persistence."""

    def list(self) -> list[ProfileItem]: ...

    def search(self, query: str) -> list[ProfileItem]: ...

    def get(self, item_id: str) -> ProfileItem: ...

    def save(self, item: ProfileItem) -> ProfileItem: ...

    def delete(self, item_id: str) -> None: ...

    def merge(
        self,
        candidate: MemoryCandidate,
        item_id: str,
    ) -> ProfileItem: ...
