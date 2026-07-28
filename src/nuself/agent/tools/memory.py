"""Memory-owned framework tool definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.tools.common import (
    json_string_tuple_filter,
    structured_tool_factory,
)
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository


@dataclass(frozen=True)
class MemoryToolSet:
    """Memory tools grouped by composition placement."""

    readonly: tuple[BaseTool, ...]
    write: tuple[BaseTool, ...]


def build_memory_tools(
    *,
    query_service: MemoryQueryService,
    repository: MemoryEntryRepository,
    project_root: Path | None,
) -> tuple[BaseTool, ...]:
    """Build the memory service's chat tools."""
    tools = build_memory_tool_set(
        query_service=query_service,
        repository=repository,
        project_root=project_root,
    )
    return tools.readonly + tools.write


def build_memory_tool_set(
    *,
    query_service: MemoryQueryService,
    repository: MemoryEntryRepository,
    project_root: Path | None,
) -> MemoryToolSet:
    """Build memory tools grouped for the public chat composition order."""
    tool_from_function = structured_tool_factory()

    def search_memory(
        query: str,
        limit: int = 8,
        types: list[str] | str | None = None,
        tags: list[str] | str | None = None,
    ) -> str:
        """Search durable memory, profile, and source chunks for relevant context."""
        try:
            query_str = str(query) if query else ""
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: invalid arguments for memory_search tool"
        if not query_str.strip():
            return "Error: query must be a non-empty string"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        packed = query_service.pack(
            MemoryQuery(
                text=query_str.strip(),
                limit=limit_int,
                memory_types=json_string_tuple_filter(types),
                tags=json_string_tuple_filter(tags),
            )
        )
        if not packed.text:
            return f"No matches found for query: {query_str}"
        return packed.text

    def count_memory(
        types: list[str] | str | None = None,
        tags: list[str] | str | None = None,
    ) -> str:
        """Count durable memory entries, optionally filtered by type or tag."""
        entries = repository.list()
        if types:
            type_set = set(json_string_tuple_filter(types))
            entries = [entry for entry in entries if entry.type in type_set]
        if tags:
            tag_set = set(json_string_tuple_filter(tags))
            entries = [
                entry for entry in entries if tag_set.intersection(entry.tags)
            ]
        suffix = (
            f" (filtered by type={types}, tags={tags})"
            if types or tags
            else ""
        )
        return f"Memory entries: {len(entries)} total{suffix}"

    def archive_memory_by_id(entry_id: str) -> str:
        """Archive a memory entry so it is excluded from default search."""
        if project_root is None:
            return "Error: project root is not configured"
        try:
            entry = repository.get(entry_id)
        except Exception as exc:
            return f"Error: could not find memory entry: {exc}"
        updated = entry.with_updates(review_state="archived")
        repository.save(updated)
        repository.reindex()
        return f'Archived "{updated.title}".'

    def update_memory_importance_by_id(
        entry_id: str,
        importance: float,
    ) -> str:
        """Update a memory entry's importance score from 0.0 to 1.0."""
        if project_root is None:
            return "Error: project root is not configured"
        try:
            importance_float = float(importance)
        except (ValueError, TypeError):
            return "Error: importance must be a number"
        if not 0.0 <= importance_float <= 1.0:
            return "Error: importance must be between 0.0 and 1.0"
        try:
            entry = repository.get(entry_id)
        except Exception as exc:
            return f"Error: could not find memory entry: {exc}"
        updated = entry.with_updates(importance=importance_float)
        repository.save(updated)
        repository.reindex()
        return (
            f'Updated importance of "{updated.title}" '
            f"to {importance_float:.2f}."
        )

    return MemoryToolSet(
        readonly=(
            tool_from_function(
                search_memory,
                name="memory_search",
                description=(
                    "Search durable memory (entries, derived profiles, and source chunks) for relevant context. "
                    "Use natural language queries to find information about preferences, beliefs, episodes, and facts. "
                    "Returns formatted memory context with matches, scores, and match reasons."
                ),
                tags=("readonly",),
                metadata={"service_component": "memory"},
            ),
            tool_from_function(
                count_memory,
                name="memory_count",
                description=(
                    "Count durable memory entries with optional type or tag filters. "
                    "Use when the user asks how many memories exist, or to get a quick count "
                    "before deciding whether to search more deeply. Returns a simple count."
                ),
                tags=("readonly",),
                metadata={"service_component": "memory"},
            ),
        ),
        write=(
            tool_from_function(
                archive_memory_by_id,
                name="memory_archive",
                description=(
                    "Archive a memory entry so it is excluded from default search and chat context. "
                    "Use when the user says a memory is outdated, no longer relevant, or should be hidden. "
                    "Requires the memory entry_id."
                ),
                tags=("write",),
                metadata={"service_component": "memory"},
            ),
            tool_from_function(
                update_memory_importance_by_id,
                name="memory_update_importance",
                description=(
                    "Adjust the importance score (0.0-1.0) of a memory entry. "
                    "Use when the user emphasizes or downplays the significance of a memory. "
                    "Requires the memory entry_id and a new importance value."
                ),
                tags=("write",),
                metadata={"service_component": "memory"},
            ),
        ),
    )
