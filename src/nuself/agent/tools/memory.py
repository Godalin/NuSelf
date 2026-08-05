"""Memory-owned framework tool definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, mutating, observed, readonly, tool
from nuself.memory.service import MemoryMatch, MemoryQuery, MemoryService
from nuself.memory.repository import MemoryEntryNotFound
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.feature.execution import FeatureExecutor


def _string_tuple_filter(
    value: list[str] | str | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in value if str(item))


def _format_match(match: MemoryMatch) -> str:
    entry = match.entry
    tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
    relations = ";".join(
        f"{name}:{','.join(targets)}"
        for name, targets in entry.relations.items()
        if targets
    )
    relation_text = f" relations={relations}" if relations else ""
    return (
        f"- {entry.title} [id={entry.id} type={entry.type} "
        f"confidence={entry.confidence:.2f}{tags}{relation_text} "
        f"match={','.join(match.reasons)}]: {entry.body}"
    )


@dataclass(frozen=True)
class MemoryToolSet:
    """Memory tools grouped by composition placement."""

    readonly: tuple[BaseTool, ...]
    write: tuple[BaseTool, ...]


def build_memory_tool_set(
    *,
    service: MemoryService,
    project_root: Path | None,
    executor: FeatureExecutor,
) -> MemoryToolSet:
    """Build memory tools grouped for the public chat composition order."""
    execution = executor
    @tool(
        name="memory_search",
        description=(
            "Search personal long-term memory for relevant context. "
            "Use natural language queries to find information about preferences, beliefs, episodes, and facts. "
            "Returns formatted memory context with matches, scores, and match reasons."
        ),
    )
    @component("memory")
    @readonly
    @observed
    def search_memory(
        query: str,
        limit: int = 8,
        types: list[str] | str | None = None,
        tags: list[str] | str | None = None,
    ) -> str:
        """Search personal long-term memory for relevant context."""
        try:
            query_str = str(query) if query else ""
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: invalid arguments for memory_search tool"
        if not query_str.strip():
            return "Error: query must be a non-empty string"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        matches = service.search(
            MemoryQuery(
                text=query_str.strip(),
                limit=limit_int,
                memory_types=_string_tuple_filter(types),
                tags=_string_tuple_filter(tags),
            )
        )
        if not matches:
            return (
                f"No matches found for query: {query_str}. "
                "If this is the first empty search for the current question, "
                "retry memory_search exactly once with a distinct broader "
                "query using fewer, shorter, or synonymous keywords."
            )
        return "\n".join(_format_match(match) for match in matches)

    @tool(
        name="memory_count",
        description=(
            "Count durable memory entries with optional type or tag filters. "
            "Use when the user asks how many memories exist, or to get a quick count "
            "before deciding whether to search more deeply. Returns a simple count."
        ),
    )
    @component("memory")
    @readonly
    @observed
    def count_memory(
        types: list[str] | str | None = None,
        tags: list[str] | str | None = None,
    ) -> str:
        """Count durable memory entries, optionally filtered by type or tag."""
        count = service.count(
            memory_types=_string_tuple_filter(types),
            tags=_string_tuple_filter(tags),
        )
        suffix = (
            f" (filtered by type={types}, tags={tags})"
            if types or tags
            else ""
        )
        return f"Memory entries: {count} total{suffix}"

    @tool(
        name="memory_archive",
        description=(
            "Archive a memory entry so it is excluded from default search and chat context. "
            "Use when the user says a memory is outdated, no longer relevant, or should be hidden. "
            "Requires the memory entry_id."
        ),
    )
    @component("memory")
    @mutating
    @observed
    def archive_memory_by_id(entry_id: str) -> str:
        """Archive a memory entry so it is excluded from default search."""
        if project_root is None:
            return "Error: project root is not configured"
        try:
            updated = service.archive(entry_id)
        except MemoryEntryNotFound as exc:
            return (
                "Error: could not find memory entry: "
                f"{diagnostic_exception_message(exc)}"
            )
        return f'Archived "{updated.title}".'

    @tool(
        name="memory_update_importance",
        description=(
            "Adjust the importance score (0.0-1.0) of a memory entry. "
            "Use when the user emphasizes or downplays the significance of a memory. "
            "Requires the memory entry_id and a new importance value."
        ),
    )
    @component("memory")
    @mutating
    @observed
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
            updated = service.update_importance(
                entry_id,
                importance=importance_float,
            )
        except MemoryEntryNotFound as exc:
            return (
                "Error: could not find memory entry: "
                f"{diagnostic_exception_message(exc)}"
            )
        return (
            f'Updated importance of "{updated.title}" '
            f"to {importance_float:.2f}."
        )

    return MemoryToolSet(
        readonly=(
            materialize_tool(search_memory, executor=execution),
            materialize_tool(count_memory, executor=execution),
        ),
        write=(
            materialize_tool(archive_memory_by_id, executor=execution),
            materialize_tool(
                update_memory_importance_by_id,
                executor=execution,
            ),
        ),
    )
