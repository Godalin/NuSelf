"""Tool definitions and execution for chat agents."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from langchain_core.tools import BaseTool, StructuredTool

from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.reason.repository import ReasonNotFound
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository
from nuself.trace.repository import TraceNotFound
from nuself.trace.service import TraceQueryService
from nuself.tui.reason import render_reason_detail, render_reason_row
from nuself.tui.trace import render_trace_detail, render_trace_row


def build_langchain_chat_tools(
    *,
    query_service: MemoryQueryService,
    reflection_repository: ReflectionRepository,
    project_root: Path | None,
) -> tuple[BaseTool, ...]:
    """Build the LangChain tool registry for the chat runtime."""

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
            return "Error: invalid arguments for search_memory tool"

        if not query_str.strip():
            return "Error: query must be a non-empty string"
        if limit_int < 1:
            return "Error: limit must be a positive integer"
        memory_query = MemoryQuery(
            text=query_str.strip(),
            limit=limit_int,
            memory_types=_string_tuple_filter(types),
            tags=_string_tuple_filter(tags),
        )
        packed = query_service.pack(memory_query)
        if not packed.text:
            return f"No matches found for query: {query_str}"
        return packed.text

    def list_pending_reflections(limit: int = 5) -> str:
        """List pending proactive reflection ideas."""

        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"

        entries = reflection_repository.list(status="pending")
        if not entries:
            return "No pending reflection ideas at the moment."

        lines: list[str] = ["Pending reflection ideas:"]
        for i, entry in enumerate(entries[:limit_int], start=1):
            lines.append(f"[{i}] {entry.title} ({entry.candidate_type}, score={entry.composite_score:.2f})")
        return "\n".join(lines)

    def dismiss_reflection_by_index(index: int) -> str:
        """Dismiss a pending reflection idea by 1-based list index."""

        try:
            idx = int(index)
        except (ValueError, TypeError):
            return "Error: index must be an integer"
        if idx < 1:
            return "Error: index must be a positive integer"

        entries = reflection_repository.list(status="pending")
        if idx > len(entries):
            return f"Error: index {idx} is out of range (only {len(entries)} pending ideas)"

        entry = entries[idx - 1]
        reflection_repository.dismiss(entry.id)
        return f'Dismissed "{entry.title}".'

    def archive_reflection_by_index(index: int) -> str:
        """Archive a pending reflection idea by 1-based list index."""

        try:
            idx = int(index)
        except (ValueError, TypeError):
            return "Error: index must be an integer"
        if idx < 1:
            return "Error: index must be a positive integer"

        entries = reflection_repository.list(status="pending")
        if idx > len(entries):
            return f"Error: index {idx} is out of range (only {len(entries)} pending ideas)"

        entry = entries[idx - 1]
        reflection_repository.archive(entry.id)
        return f'Archived "{entry.title}". The discussion has been captured into memory through the conversation.'

    def count_memory(types: list[str] | str | None = None, tags: list[str] | str | None = None) -> str:
        """Count durable memory entries, optionally filtered by type or tag."""

        repo = MemoryEntryRepository(project_root)
        entries = repo.list()
        if types:
            type_set = set(_string_tuple_filter(types))
            entries = [e for e in entries if e.type in type_set]
        if tags:
            tag_set = set(_string_tuple_filter(tags))
            entries = [e for e in entries if tag_set.intersection(e.tags)]
        return f"Memory entries: {len(entries)} total" + (f" (filtered by type={types}, tags={tags})" if types or tags else "")

    def archive_memory_by_id(entry_id: str) -> str:
        """Archive a memory entry so it is excluded from default search."""

        if project_root is None:
            return "Error: project root is not configured"
        try:
            repo = MemoryEntryRepository(project_root)
            entry = repo.get(entry_id)
        except Exception as e:
            return f"Error: could not find memory entry: {e}"
        updated = entry.with_updates(review_state="archived")
        repo.save(updated)
        repo.reindex()
        return f'Archived "{updated.title}".'

    def update_memory_importance_by_id(entry_id: str, importance: float) -> str:
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
            repo = MemoryEntryRepository(project_root)
            entry = repo.get(entry_id)
        except Exception as e:
            return f"Error: could not find memory entry: {e}"
        updated = entry.with_updates(importance=importance_float)
        repo.save(updated)
        repo.reindex()
        return f'Updated importance of "{updated.title}" to {importance_float:.2f}.'

    def list_active_reasoning_threads() -> str:
        """List active and paused long-run reasoning threads."""

        service = ReasonService(project_root)
        threads = service.list_threads()
        if not threads:
            return "No active or paused reasoning threads."
        lines = ["Active and paused reasoning threads:"]
        for index, thread in enumerate(threads, start=1):
            steps = service.list_steps(thread.id)
            row = render_reason_row(thread, index=index)
            lines.append(f"{row}\n  steps={len(steps)}")
        return "\n".join(lines)

    def show_reasoning_thread(thread_id: str) -> str:
        """Show one long-run reasoning thread."""

        if not thread_id.strip():
            return "Error: thread_id must be a non-empty string"
        service = ReasonService(project_root)
        try:
            thread = service.show_thread(thread_id.strip())
        except ReasonNotFound as exc:
            return f"Error: {exc}"
        return render_reason_detail(thread, service.list_steps(thread.id))

    def search_trace(query: str, limit: int = 5) -> str:
        """Search thought provenance trace records."""

        query_str = str(query) if query else ""
        if not query_str.strip():
            return "Error: query must be a non-empty string"
        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"

        traces = TraceQueryService(project_root).search_traces(query_str.strip())[:limit_int]
        if not traces:
            return f"No trace records matched: {query_str}"
        lines = ["Matching trace records:"]
        for index, trace in enumerate(traces, start=1):
            lines.append(render_trace_row(trace, index=index))
        return "\n".join(lines)

    def show_trace(trace_id: str) -> str:
        """Show one thought provenance trace record."""

        if not trace_id.strip():
            return "Error: trace_id must be a non-empty string"
        service = TraceQueryService(project_root)
        try:
            trace = service.show_trace(trace_id.strip())
        except TraceNotFound as exc:
            return f"Error: {exc}"
        return render_trace_detail(trace, service.links_for(trace.id))

    structured_tool = cast(Callable[..., StructuredTool], getattr(StructuredTool, "from_function"))
    return (
        structured_tool(
            search_memory,
            name="search_memory",
            description=(
                "Search durable memory (entries, derived profiles, and source chunks) for relevant context. "
                "Use natural language queries to find information about preferences, beliefs, episodes, and facts. "
                "Returns formatted memory context with matches, scores, and match reasons."
            ),
        ),
        structured_tool(
            count_memory,
            name="count_memory",
            description=(
                "Count durable memory entries with optional type or tag filters. "
                "Use when the user asks how many memories exist, or to get a quick count "
                "before deciding whether to search more deeply. Returns a simple count."
            ),
        ),
        structured_tool(
            list_pending_reflections,
            name="list_pending_reflections",
            description=(
                "List pending proactive reflection ideas (questions, connections, contradictions) "
                "generated from the user's memory and conversations. Use when the user seems open "
                "to exploring new topics, or when the conversation naturally pauses. "
                "Returns a numbered list with title, type, and confidence."
            ),
        ),
        structured_tool(
            dismiss_reflection_by_index,
            name="dismiss_reflection",
            description=(
                "Dismiss a pending reflection idea so it will no longer be suggested. "
                "Use when the user explicitly says they are not interested in a topic. "
                "The index corresponds to the numbered list from list_pending_reflections."
            ),
        ),
        structured_tool(
            archive_reflection_by_index,
            name="archive_reflection",
            description=(
                "Archive a pending reflection idea after the discussion is complete. "
                "Use when the user has engaged with a reflection idea and the topic feels resolved. "
                "The index corresponds to the numbered list shown in the pending reflections context."
            ),
        ),
        structured_tool(
            archive_memory_by_id,
            name="archive_memory",
            description=(
                "Archive a memory entry so it is excluded from default search and chat context. "
                "Use when the user says a memory is outdated, no longer relevant, or should be hidden. "
                "Requires the memory entry_id."
            ),
        ),
        structured_tool(
            update_memory_importance_by_id,
            name="update_memory_importance",
            description=(
                "Adjust the importance score (0.0-1.0) of a memory entry. "
                "Use when the user emphasizes or downplays the significance of a memory. "
                "Requires the memory entry_id and a new importance value."
            ),
        ),
        structured_tool(
            list_active_reasoning_threads,
            name="list_active_reasoning_threads",
            description=(
                "List active and paused long-run reasoning threads. Use when the user asks about "
                "open questions, ongoing thinking, active reason threads, or what NuSelf is still considering."
            ),
        ),
        structured_tool(
            show_reasoning_thread,
            name="show_reasoning_thread",
            description=(
                "Show details for a specific long-run reasoning thread, including summary, hypotheses, "
                "open questions, evidence refs, and recent steps. Requires a thread_id."
            ),
        ),
        structured_tool(
            search_trace,
            name="search_trace",
            description=(
                "Search NuSelf thought provenance records. Use when the user asks where an idea came from, "
                "how a belief or answer formed, or what prior records support a conclusion."
            ),
        ),
        structured_tool(
            show_trace,
            name="show_trace",
            description=(
                "Show a specific thought provenance trace record with related links. Requires a trace_id."
            ),
        ),
    )


def _string_tuple_filter(value: list[str] | str | None) -> tuple[str, ...]:
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
