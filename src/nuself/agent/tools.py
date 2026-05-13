"""Tool definitions and execution for chat agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.notification import NotificationOutbox


class Tool(Protocol):
    """Protocol for chat agent tools."""

    name: str
    description: str

    def invoke(self, *args: object, **kwargs: object) -> str:
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


@dataclass(frozen=True)
class ListPendingReflectionsTool:
    """Tool for listing pending reflection ideas from the outbox."""

    outbox: NotificationOutbox
    name: str = "list_pending_reflections"
    description: str = (
        "List pending proactive reflection ideas (questions, connections, contradictions) "
        "generated from the user's memory and conversations. Use when the user seems open "
        "to exploring new topics, or when the conversation naturally pauses. "
        "Returns a numbered list with title, type, and confidence."
    )

    def invoke(self, limit: int = 5) -> str:
        """List pending reflection ideas.

        Args:
            limit: Maximum number of ideas to return (default 5).

        Returns:
            Numbered list of pending ideas, or a message indicating none are available.
        """
        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"

        entries = self.outbox.list(status="pending")
        if not entries:
            return "No pending reflection ideas at the moment."

        lines: list[str] = ["Pending reflection ideas:"]
        for i, entry in enumerate(entries[:limit_int], start=1):
            lines.append(f"[{i}] {entry.title}")
        return "\n".join(lines)


@dataclass(frozen=True)
class DismissReflectionTool:
    """Tool for dismissing a pending reflection idea."""

    outbox: NotificationOutbox
    name: str = "dismiss_reflection"
    description: str = (
        "Dismiss a pending reflection idea so it will no longer be suggested. "
        "Use when the user explicitly says they are not interested in a topic. "
        "The index corresponds to the numbered list from list_pending_reflections."
    )

    def invoke(self, index: int) -> str:
        """Dismiss a reflection idea by its 1-based index.

        Args:
            index: 1-based index from list_pending_reflections output.

        Returns:
            Confirmation or error message.
        """
        try:
            idx = int(index)
        except (ValueError, TypeError):
            return "Error: index must be an integer"
        if idx < 1:
            return "Error: index must be a positive integer"

        entries = self.outbox.list(status="pending")
        if idx > len(entries):
            return f"Error: index {idx} is out of range (only {len(entries)} pending ideas)"

        entry = entries[idx - 1]
        self.outbox.dismiss(entry.id)
        return f'Dismissed "{entry.title}".'


def get_tool_description(tool: Tool) -> dict[str, Any]:
    """Get a description dict for a tool to include in prompts."""
    return {
        "name": tool.name,
        "description": tool.description,
        "usage": f'Call with {{"tool": "{tool.name}", "args": {{...arguments...}}}}',
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
