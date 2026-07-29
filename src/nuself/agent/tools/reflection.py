"""Reflection-owned framework tool definitions."""

from __future__ import annotations

from importlib import import_module

from langchain_core.tools import BaseTool

from nuself.agent.tools.common import structured_tool_factory
from nuself.handles import VisibleHandleError, parse_visible_index
from nuself.reflection.repository import ReflectionRepository
from nuself.runtime.diagnostics import diagnostic_exception_message


def build_reflection_tools(
    repository: ReflectionRepository,
) -> tuple[BaseTool, ...]:
    """Build the reflection service's chat tools."""
    tool_from_function = structured_tool_factory()

    def count_pending_reflections() -> str:
        """Count pending proactive reflection ideas."""
        return (
            "Pending reflection ideas: "
            f"{len(repository.list(status='pending'))} total"
        )

    def list_pending_reflections(limit: int = 5) -> str:
        """List pending proactive reflection ideas."""
        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        entries = repository.list(status="pending")
        if not entries:
            return "No pending reflection ideas at the moment."
        lines = ["Pending reflection ideas:"]
        for index, entry in enumerate(entries[:limit_int]):
            lines.append(
                f"[{index}] {entry.title} "
                f"({entry.candidate_type}, score={entry.composite_score:.2f})"
            )
        return "\n".join(lines)

    def dismiss_reflection_by_numeric_handle(index: int) -> str:
        """Dismiss a pending reflection idea by 0-based list index."""
        try:
            entries = repository.list(status="pending")
            selected = parse_visible_index(
                str(index),
                count=len(entries),
                label="reflection",
            )
        except VisibleHandleError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        except (ValueError, TypeError):
            return "Error: index must be an integer"
        entry = entries[selected]
        repository.dismiss(entry.id)
        return f'Dismissed "{entry.title}".'

    def archive_reflection_by_numeric_handle(index: int) -> str:
        """Archive a pending reflection idea by 0-based list index."""
        try:
            entries = repository.list(status="pending")
            selected = parse_visible_index(
                str(index),
                count=len(entries),
                label="reflection",
            )
        except VisibleHandleError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        except (ValueError, TypeError):
            return "Error: index must be an integer"
        entry = entries[selected]
        repository.archive(entry.id)
        return (
            f'Archived "{entry.title}". The discussion has been captured '
            "into memory through the conversation."
        )

    decorators = import_module("nuself.decorators")
    composed_dismiss = decorators.approval_required("reflection")(
        dismiss_reflection_by_numeric_handle
    )
    return (
        tool_from_function(
            list_pending_reflections,
            name="reflection_list_pending",
            description=(
                "List pending proactive reflection ideas (questions, connections, contradictions) "
                "generated from the user's memory and conversations. Use when the user seems open "
                "to exploring new topics, or when the conversation naturally pauses. "
                "Returns a 0-based numbered list with title, type, and confidence."
            ),
            tags=("readonly",),
            metadata={"service_component": "reflection"},
        ),
        tool_from_function(
            count_pending_reflections,
            name="reflection_count",
            description=(
                "Count pending proactive reflection ideas. Use when the user asks how many ideas, thoughts, "
                "or pending reflections are currently available."
            ),
            tags=("readonly",),
            metadata={"service_component": "reflection"},
        ),
        tool_from_function(
            composed_dismiss,
            name="reflection_dismiss",
            description=(
                "Dismiss a pending reflection idea so it will no longer be suggested. "
                "Use when the user explicitly says they are not interested in a topic. "
                "The 0-based index corresponds to the numbered list from reflection_list_pending."
            ),
            tags=("write",),
            metadata={"service_component": "reflection"},
        ),
        tool_from_function(
            archive_reflection_by_numeric_handle,
            name="reflection_archive",
            description=(
                "Archive a pending reflection idea after the discussion is complete. "
                "Use when the user has engaged with a reflection idea and the topic feels resolved. "
                "The 0-based index corresponds to the numbered list shown in the pending reflections context."
            ),
            tags=("write",),
            metadata={"service_component": "reflection"},
        ),
    )
