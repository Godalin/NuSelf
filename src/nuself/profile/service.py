"""User-intent operations for derived profile items."""

from __future__ import annotations

from nuself.profile.model import ProfileItem
from nuself.profile.repository import ProfileItemRepository, ProfileSearchFilters


class ProfileService:
    """Inspect and maintain profile items without exposing persistence."""

    def __init__(self, repository: ProfileItemRepository) -> None:
        self._repository = repository

    def list_items(self) -> list[ProfileItem]:
        return self._repository.list()

    def search_items(
        self,
        query: str,
        filters: ProfileSearchFilters | None = None,
    ) -> list[ProfileItem]:
        return self._repository.search(query, filters)

    def search(self, query: str) -> list[ProfileItem]:
        """Search profile context for a cross-domain consumer."""

        return self._repository.search(query)

    def get_item(self, item_id: str) -> ProfileItem:
        return self._repository.get(item_id)

    def delete_item(self, item_id: str) -> None:
        self._repository.delete(item_id)
