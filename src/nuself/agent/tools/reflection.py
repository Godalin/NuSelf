"""Reflection-owned framework tool definitions."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import (
    confirmed,
    component,
    mutating,
    observed,
    readonly,
    tool,
)
from nuself.reflection.repository import ReflectionEntryNotFound
from nuself.reflection.service import ReflectionService
from nuself.runtime.feature.execution import FeatureExecutor


def build_reflection_tools(
    service: ReflectionService,
    *,
    executor: FeatureExecutor,
) -> tuple[BaseTool, ...]:
    """Build the reflection service's chat tools."""
    execution = executor

    @tool(
        name="reflection_count",
        description=(
            "Count pending proactive reflection ideas. Use when the user asks how many ideas, thoughts, "
            "or pending reflections are currently available."
        ),
    )
    @component("reflection")
    @readonly
    @observed
    def count_pending_reflections() -> str:
        """Count pending proactive reflection ideas."""
        return (
            "Pending reflection ideas: "
            f"{len(service.list_entries(status='pending'))} total"
        )

    @tool(
        name="reflection_list_pending",
        description=(
            "List pending proactive reflection ideas (questions, connections, contradictions) "
            "generated from the user's memory and conversations. Use when the user seems open "
            "to exploring new topics, or when the conversation naturally pauses. "
            "Returns a 0-based numbered list with title, type, and confidence."
        ),
    )
    @component("reflection")
    @readonly
    @observed
    def list_pending_reflections(limit: int = 5) -> str:
        """List pending proactive reflection ideas."""
        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        entries = service.list_entries(status="pending")
        if not entries:
            return "No pending reflection ideas at the moment."
        lines = ["Pending reflection ideas:"]
        for index, entry in enumerate(entries[:limit_int]):
            lines.append(
                f"[{index}] id={entry.id} {entry.title} "
                f"({entry.candidate_type}, score={entry.composite_score:.2f})"
            )
        return "\n".join(lines)

    @tool(
        name="reflection_dismiss",
        description=(
            "Dismiss a pending reflection idea so it will no longer be suggested. "
            "Use when the user explicitly says they are not interested in a topic. "
            "Pass the stable entry id returned by reflection_list_pending."
        ),
    )
    @component("reflection")
    @mutating
    @confirmed(action="dismiss", resource="reflection")
    @observed
    def dismiss_reflection(entry_id: str) -> str:
        """Dismiss a pending reflection idea by durable entry id."""
        try:
            entry = service.get_entry(entry_id.strip())
        except ReflectionEntryNotFound:
            return f"Error: reflection not found: {entry_id}"
        service.dismiss_entry(entry.id)
        return f'Dismissed "{entry.title}".'

    @tool(
        name="reflection_archive",
        description=(
            "Archive a pending reflection idea after the discussion is complete. "
            "Use when the user has engaged with a reflection idea and the topic feels resolved. "
            "Pass the stable entry id returned by reflection_list_pending."
        ),
    )
    @component("reflection")
    @mutating
    @observed
    def archive_reflection(entry_id: str) -> str:
        """Archive a pending reflection idea by durable entry id."""
        try:
            entry = service.get_entry(entry_id.strip())
        except ReflectionEntryNotFound:
            return f"Error: reflection not found: {entry_id}"
        service.archive_entry(entry.id)
        return (
            f'Archived "{entry.title}". The discussion has been captured '
            "into memory through the conversation."
        )

    return (
        materialize_tool(list_pending_reflections, executor=execution),
        materialize_tool(count_pending_reflections, executor=execution),
        materialize_tool(
            dismiss_reflection,
            executor=execution,
        ),
        materialize_tool(
            archive_reflection,
            executor=execution,
        ),
    )
