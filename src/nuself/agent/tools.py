"""Tool definitions and execution for chat agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from nuself.memory.query import MemoryQuery, MemoryQueryService


class Tool(Protocol):
    """Protocol for chat agent tools."""

    name: str
    description: str

    def invoke(self, **kwargs: object) -> str:
        """Invoke the tool with the given arguments. Returns a string result."""
        ...


@dataclass(frozen=True)
class MemorySearchTool:
    """Tool for searching durable memory, profiles, and sources."""

    query_service: MemoryQueryService
    name: str = "search_memory"
    description: str = (
        "Search durable memory (entries, derived profiles, and source chunks) for relevant context. "
        "Use natural language queries to find information about preferences, beliefs, episodes, and facts. "
        "Returns formatted memory context with matches, scores, and match reasons."
    )

    def invoke(
        self,
        query: str = "",
        limit: int = 8,
        types: list[str] | tuple[str, ...] | str | None = None,
        tags: list[str] | tuple[str, ...] | str | None = None,
    ) -> str:
        """Search memory and return formatted results.

        Args:
            query: Natural language search query (e.g., 'my work preferences', 'Python experience').
            limit: Maximum number of results to return (default 8).
            types: Optional memory type or list of memory types to include.
            tags: Optional tag or list of tags that results must include.

        Returns:
            Formatted memory context as string, or empty string if no matches found.
        """
        # Validate inputs
        try:
            query_str = str(query) if query else ""
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: invalid arguments for search_memory tool"

        if not query_str.strip():
            return "Error: query must be a non-empty string"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        type_filters = _string_tuple_filter(types)
        tag_filters = _string_tuple_filter(tags)

        memory_query = MemoryQuery(
            text=query_str.strip(),
            limit=limit_int,
            memory_types=type_filters,
            tags=tag_filters,
        )
        packed = self.query_service.pack(memory_query)

        if not packed.text:
            return f"No matches found for query: {query_str}"

        return packed.text


def get_tool_description(tool: Tool) -> dict[str, Any]:
    """Get a description dict for a tool to include in prompts."""
    return {
        "name": tool.name,
        "description": tool.description,
        "usage": f"Call with {{\"tool\": \"{tool.name}\", \"args\": {{...arguments...}}}}",
    }


def _string_tuple_filter(value: list[str] | tuple[str, ...] | str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    result: list[str] = []
    for item in value:
        if item.strip():
            result.append(item.strip())
    return tuple(result)
