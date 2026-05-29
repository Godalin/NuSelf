"""Tool definitions and execution for chat agents."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool

from nuself.handles import VisibleHandleError, parse_visible_index
from nuself.logs import write_log_event
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonNotFound
from nuself.reason.service import ReasonService
from nuself.store import ScopedWorkspace
from nuself.reflection.repository import ReflectionRepository
from nuself.trace.repository import TraceNotFound
from nuself.trace.service import TraceQueryService
from nuself.tui.trace import render_trace_detail, render_trace_row
from nuself.persona.tools import build_persona_tools

StructuredToolFactory = Callable[..., StructuredTool]


def build_langchain_chat_tools(
    *,
    query_service: MemoryQueryService,
    reflection_repository: ReflectionRepository,
    project_root: Path | None,
    selves_consult: Callable[[str, str, str | None], str] | None = None,
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
            return "Error: invalid arguments for memory_search tool"

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

    def count_pending_reflections() -> str:
        """Count pending proactive reflection ideas."""

        return f"Pending reflection ideas: {len(reflection_repository.list(status='pending'))} total"

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
        for i, entry in enumerate(entries[:limit_int]):
            lines.append(f"[{i}] {entry.title} ({entry.candidate_type}, score={entry.composite_score:.2f})")
        return "\n".join(lines)

    def dismiss_reflection_by_numeric_handle(index: int) -> str:
        """Dismiss a pending reflection idea by 0-based list index."""

        try:
            entries = reflection_repository.list(status="pending")
            idx = parse_visible_index(str(index), count=len(entries), label="reflection")
        except VisibleHandleError as exc:
            return f"Error: {exc}"
        except (ValueError, TypeError):
            return "Error: index must be an integer"

        entry = entries[idx]
        reflection_repository.dismiss(entry.id)
        return f'Dismissed "{entry.title}".'

    def archive_reflection_by_numeric_handle(index: int) -> str:
        """Archive a pending reflection idea by 0-based list index."""

        try:
            entries = reflection_repository.list(status="pending")
            idx = parse_visible_index(str(index), count=len(entries), label="reflection")
        except VisibleHandleError as exc:
            return f"Error: {exc}"
        except (ValueError, TypeError):
            return "Error: index must be an integer"

        entry = entries[idx]
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
            return _json_result({"threads": [], "count": 0})
        return _json_result(
            {
                "threads": [
                    {
                        "index": index,
                        "id": thread.id,
                        "topic": thread.topic,
                        "status": thread.status,
                        "priority": thread.priority,
                        "working_summary": thread.working_summary,
                        "step_count": len(service.list_steps(thread.id)),
                        "created_at": thread.created_at,
                        "last_advanced_at": thread.last_advanced_at,
                    }
                    for index, thread in enumerate(threads)
                ],
                "count": len(threads),
            }
        )

    def count_reasoning_threads() -> str:
        """Count active and paused long-run reasoning threads."""

        threads = ReasonService(project_root).list_threads()
        by_status: dict[str, int] = {}
        for thread in threads:
            by_status[thread.status] = by_status.get(thread.status, 0) + 1
        return _json_result({"count": len(threads), "by_status": by_status})

    def show_reasoning_thread(thread_id: str) -> str:
        """Show one long-run reasoning thread. Use "current" to show the most recent active thread."""

        tid = thread_id.strip()
        if not tid:
            return "Error: thread_id must be a non-empty string"
        service = ReasonService(project_root)
        if tid.lower() == "current":
            threads = service.list_threads()
            if not threads:
                return _json_error("No active reasoning threads.")
            thread = threads[-1]
            return _json_result(_reason_show_payload(thread, service.list_steps(thread.id)))
        try:
            thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(str(exc))
        return _json_result(_reason_show_payload(thread, service.list_steps(thread.id)))

    def show_reasoning_context(thread_id: str) -> str:
        """Show one reasoning thread's global settings and current state, excluding step bodies and tool logs."""

        tid = thread_id.strip()
        if not tid:
            return _json_error("thread_id must be a non-empty string")
        service = ReasonService(project_root)
        try:
            if tid.lower() == "current":
                threads = service.list_threads()
                if not threads:
                    return _json_error("No active reasoning threads.")
                thread = threads[-1]
            else:
                thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(str(exc))
        steps = service.list_steps(thread.id)
        return _json_result(
            {
                "thread": _reason_thread_payload(thread),
                "step_count": len(steps),
                "tool_logs": "omitted",
            }
        )

    def show_reasoning_step(thread_id: str, step: str) -> str:
        """Show one reasoning step by 0-based index, step id, or 'latest'. Tool logs are omitted."""

        tid = thread_id.strip()
        step_ref = step.strip()
        if not tid:
            return _json_error("thread_id must be a non-empty string")
        if not step_ref:
            return _json_error("step must be a non-empty string")
        service = ReasonService(project_root)
        try:
            if tid.lower() == "current":
                threads = service.list_threads()
                if not threads:
                    return _json_error("No active reasoning threads.")
                thread = threads[-1]
            else:
                thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(str(exc))
        steps = service.list_steps(thread.id)
        if not steps:
            return _json_error(f"No reasoning steps for thread: {thread.id}")
        if step_ref.lower() == "latest":
            index = len(steps) - 1
            selected = steps[index]
        elif step_ref.isdigit():
            try:
                index = parse_visible_index(step_ref, count=len(steps), label="reason step")
            except VisibleHandleError as exc:
                return _json_error(str(exc))
            selected = steps[index]
        else:
            matches = [candidate for candidate in steps if candidate.id == step_ref]
            if not matches:
                return _json_error(f"reason step not found: {step_ref}")
            selected = matches[0]
            index = steps.index(selected)
        return _json_result(
            {
                "thread": {"id": thread.id, "topic": thread.topic, "status": thread.status},
                "step": _reason_step_payload(selected, index=index),
                "tool_logs": "omitted",
            }
        )

    def reason_propose(
        topic: str,
        working_summary: str,
        active_items: list[dict[str, object]],
        mandates: list[str],
    ) -> str:
        """Propose creating a long-run reasoning thread and start it after confirmation.

        Parameters:
          topic – the core topic for the thread.
          working_summary – enriched context from the discussion.
          active_items – initial tracked items, each with "label" (required),
            "description" (optional), "kind" (optional free-text tag).
            The kind tag adapts to the task (e.g. "hypothesis", "character",
            "suspect", "plot_thread", "world_rule", etc.).
          mandates – required actions the advancer MUST follow on every
            advance (e.g. ["use persona_craft to create at least one new
            persona before each advance"]).
        """

        topic = topic.strip()
        if not topic:
            return "Error: topic must be a non-empty string"

        # Validate active thread cap before creating a proposal.
        service = ReasonService(project_root)
        active = service.list_threads()
        if len(active) >= 5:
            lines = [f"Cannot start new thread: already {len(active)} active threads (max 5). Please pause, resolve, or archive one first.", "Active threads:"]
            for t in active:
                lines.append(f"  - {t.id}: {t.topic[:60]}")
            return "\n".join(lines)

        proposal_id = uuid4().hex[:12]
        write_log_event(
            "reasoning",
            "proposal_created",
            f"Reasoning thread proposal: {topic[:60]}",
            project_root=project_root,
            metadata={
                "proposal_id": proposal_id,
                "topic": topic,
                "working_summary": working_summary.strip(),
                "active_items": active_items,
                "mandates": mandates,
                "evidence_refs": [],
            },
        )
        thread = service.start_thread(
            topic=topic,
            working_summary=working_summary,
            active_items=tuple(active_items),
            mandates=tuple(mandates),
        )
        return thread.id

    def reason_export(
        thread_id: str,
        mode: str = "narrative",
        output_format: str = "markdown",
        start_index: int = 0,
        end_index: int | None = None,
        segment_size: int = 5,
    ) -> str:
        """Start a reason output export job and compose artifacts using the LLM-driven runner."""

        tid = thread_id.strip()
        if not tid:
            return "Error: thread_id must be a non-empty string"
        try:
            service = ReasonOutputService(project_root)
            manifest = service.plan_job(
                tid,
                mode=mode,
                output_format=output_format,
                start_index=int(start_index),
                end_index=int(end_index) if end_index is not None else None,
                segment_size=int(segment_size),
            )
        except (ReasonNotFound, RuntimeError, ValueError, TypeError) as exc:
            return _json_error(str(exc))

        # Compose using an LLM-driven runner (one LLM call per segment). No template fallback.
        from nuself.llm import default_llm, ChatMessage

        def _llm_runner(thread, manifest, steps, *, index, total):
            # Build a simple system + user prompt for composing a chunk from steps
            sys = (
                f"You are a writing assistant. Compose a {manifest.mode} in {manifest.output_format} format "
                "from the provided reason steps. Produce Markdown suitable for direct display."
            )
            pieces: list[ChatMessage] = [ChatMessage(role="system", content=sys)]
            body_lines: list[str] = [f"Chunk {index+1}/{total} - compose from steps:"]
            for s in steps:
                body_lines.append("---")
                body_lines.append(f"Step: {s.summary}")
                if s.output:
                    body_lines.append(s.output)
                elif s.delta:
                    body_lines.append(s.delta)
                if s.evidence_refs:
                    body_lines.append("Evidence:")
                    body_lines.extend(f"- {r}" for r in s.evidence_refs)
            user = "\n".join(body_lines)
            pieces.append(ChatMessage(role="user", content=user))
            llm = default_llm(project_root)
            return llm.complete(pieces)

        try:
            composed = service.compose_with_runner(tid, manifest.job_id, _llm_runner)
        except Exception as exc:  # catch runtime issues from LLM/agent
            return _json_error(str(exc))
        paths = service.job_paths(tid, manifest.job_id)
        return _json_result({"job": composed.to_wire(), "paths": {"root": str(paths.root), "manifest": str(paths.manifest), "progress": str(paths.progress), "combined": str(paths.combined), "chunks_dir": str(paths.chunks_dir)}})

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
        for index, trace in enumerate(traces):
            lines.append(render_trace_row(trace, index=index, color=False))
        return "\n".join(lines)

    def count_traces(query: str | None = None) -> str:
        """Count thought provenance trace records, optionally matching a query."""

        service = TraceQueryService(project_root)
        query_str = query.strip() if isinstance(query, str) else ""
        traces = service.search_traces(query_str) if query_str else service.list_traces()
        suffix = f' matching "{query_str}"' if query_str else ""
        return f"Trace records{suffix}: {len(traces)} total"

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

    def related_traces(artifact_ref: str, limit: int = 5) -> str:
        """List thought provenance records related to an artifact reference."""

        artifact = artifact_ref.strip()
        if not artifact:
            return "Error: artifact_ref must be a non-empty string"
        try:
            limit_int = int(limit)
        except (ValueError, TypeError):
            return "Error: limit must be an integer"
        if limit_int < 1:
            return "Error: limit must be a positive integer"

        service = TraceQueryService(project_root)
        traces = service.traces_for_artifact(artifact)[:limit_int]
        links = service.links_for_artifact(artifact)
        if not traces and not links:
            return f"No trace records or links related to: {artifact}"
        lines = [f"Trace records related to {artifact}:"]
        for index, trace in enumerate(traces):
            lines.append(render_trace_row(trace, index=index, color=False))
        if links:
            lines.append("Related links:")
            lines.extend(f"  {link.relation}: {link.source_id} -> {link.target_id} ({link.summary})" for link in links)
        return "\n".join(lines)

    def consult_selves(topic: str, mode: str = "consult", context: str | None = None) -> str:
        """Invoke NuSelf's internal multi-persona subagent for perspective synthesis."""

        if selves_consult is None:
            return "Error: selves consultation service is not configured"
        topic_str = str(topic) if topic else ""
        if not topic_str.strip():
            return "Error: topic must be a non-empty string"
        mode_str = str(mode) if mode else "consult"
        context_str = str(context) if context is not None else None
        return selves_consult(topic_str.strip(), mode_str.strip() or "consult", context_str)

    tool_from_function = _structured_tool_factory()

    # Compose decorators at the tool-construction site so the runtime receives
    # an already-decorated callable. Do this before constructing the `tools`
    # list to avoid embedding decorator composition inside a list literal.
    from importlib import import_module

    _decorators = import_module("nuself.decorators")
    _composed_reason_propose = _decorators.audit_log("reasoning")(_decorators.approval_required("reasoning")(reason_propose))
    _composed_reflection_dismiss = _decorators.audit_log("reflection")(_decorators.approval_required("reflection")(dismiss_reflection_by_numeric_handle))

    tools: list[BaseTool] = [
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
        ),
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
        ),
        tool_from_function(
            count_pending_reflections,
            name="reflection_count",
            description=(
                "Count pending proactive reflection ideas. Use when the user asks how many ideas, thoughts, "
                "or pending reflections are currently available."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            _composed_reflection_dismiss,
            name="reflection_dismiss",
            description=(
                "Dismiss a pending reflection idea so it will no longer be suggested. "
                "Use when the user explicitly says they are not interested in a topic. "
                "The 0-based index corresponds to the numbered list from reflection_list_pending."
            ),
            tags=("write",),
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
        ),
        tool_from_function(
            archive_memory_by_id,
            name="memory_archive",
            description=(
                "Archive a memory entry so it is excluded from default search and chat context. "
                "Use when the user says a memory is outdated, no longer relevant, or should be hidden. "
                "Requires the memory entry_id."
            ),
            tags=("write",),
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
        ),
        tool_from_function(
            list_active_reasoning_threads,
            name="reason_list_active",
            description=(
                "List active and paused long-run reasoning threads. Use when the user asks about "
                "open questions, ongoing thinking, active reason threads, or what NuSelf is still considering."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            count_reasoning_threads,
            name="reason_count",
            description=(
                "Count active and paused long-run reasoning threads. Use when the user asks how many open "
                "questions or reasoning threads NuSelf is tracking."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            show_reasoning_thread,
            name="reason_show",
            description=(
                "Show details for a specific long-run reasoning thread, including current state and steps, "
                "but omitting tool logs. Pass 'current' to show the most recent active thread."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            show_reasoning_context,
            name="reason_context",
            description=(
                "Show one reasoning thread's global setup and current state only: topic, summary, mandates, "
                "active items, pending items, next steps, reasoning prompt, evidence refs, and step count. "
                "Does not include step bodies or tool logs. Pass 'current' to show the most recent active thread."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            show_reasoning_step,
            name="reason_step",
            description=(
                "Show one concrete reasoning step by 0-based step index, step id, or 'latest'. "
                "Returns the step summary, output, delta, findings, pending items, next steps, confidence, "
                "and evidence refs, but omits tool logs."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            _composed_reason_propose,
            name="reason_propose",
            description=(
                "Propose creating a new long-run thinking thread. "
                "Call this when the user explicitly wants to start a thread. "
                "The decorated tool wrapper will prompt for confirmation before writing the proposal. "
                "The thread tracks state as general-purpose tracked items (active_items, "
                "pending_items, next_steps) with free-text kind labels that adapt to the task "
                "— e.g. 'hypothesis', 'character', 'suspect', 'plot_thread', 'world_rule'. "
                "Tip: before proposing, consider using persona_list and persona_think to "
                "enrich the thread's initial context with different perspectives."
            ),
            tags=("write",),
        ),
        tool_from_function(
            reason_export,
            name="reason_export",
            description=(
                "Start a reason output export job for a thread and write the export workspace artifacts. "
                "Use when the user wants a long-form report, narrative, outline, or summary derived from a reason thread. "
                "Returns the export job manifest and workspace paths, while the full composed output is stored in the thread workspace."
            ),
            tags=("write",),
        ),
        tool_from_function(
            search_trace,
            name="trace_search",
            description=(
                "Search NuSelf thought provenance records. Use when the user asks where an idea came from, "
                "how a belief or answer formed, or what prior records support a conclusion."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            count_traces,
            name="trace_count",
            description=(
                "Count thought provenance trace records, optionally matching a query. Use when the user asks "
                "how many provenance records exist or match a topic."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            show_trace,
            name="trace_show",
            description=(
                "Show a specific thought provenance trace record with related links. Requires a trace_id."
            ),
            tags=("readonly",),
        ),
        tool_from_function(
            related_traces,
            name="trace_related",
            description=(
                "List trace records and links that directly mention an artifact reference such as memory:<id>, "
                "reflection:<id>, reason:<id>, reason_step:<id>, persona_prompt:<id>, or trace:<id>."
            ),
            tags=("readonly",),
        ),
    ]
    if selves_consult is not None:
        tools.append(
            tool_from_function(
                consult_selves,
                name="selves_consult",
                description=(
                    "Invoke NuSelf's internal multi-persona subagent for perspective synthesis. "
                    "Use for explicit multi-perspective requests, complex design tradeoffs, value conflicts, "
                    "emotionally loaded reflection, self-model questions, or when the user asks for inner discussion. "
                    "Do not use for direct service status/count/search questions."
                ),
                tags=("readonly",),
            )
        )
    persona_tools = build_persona_tools(project_root)
    _SERVICE_BY_TOOL: dict[str, str] = {
        "memory_search": "memory",
        "memory_count": "memory",
        "memory_archive": "memory",
        "memory_update_importance": "memory",
        "reflection_list_pending": "reflection",
        "reflection_count": "reflection",
        "reflection_dismiss": "reflection",
        "reflection_archive": "reflection",
        "reason_list_active": "reasoning",
        "reason_count": "reasoning",
        "reason_context": "reasoning",
        "reason_step": "reasoning",
        "reason_show": "reasoning",
        "reason_propose": "reasoning",
        "reason_export": "reasoning",
        "trace_search": "trace",
        "trace_count": "trace",
        "trace_show": "trace",
        "trace_related": "trace",
        "selves_consult": "selves",
    }
    for tool in tools:
        service = _SERVICE_BY_TOOL.get(tool.name)
        if service:
            tool.metadata = {"service_component": service}  # pyright: ignore[reportAttributeAccessIssue]
    return tuple(tools) + persona_tools


def build_workspace_tools(
    workspace: ScopedWorkspace,
) -> tuple[BaseTool, ...]:
    """Build LangChain tools for a thread-scoped workspace.

    The caller provides a ``ScopedWorkspace`` (obtained via
    ``service.workspace(thread_id)``) and receives StructuredTool instances
    that the agent can call to store, retrieve, search, and delete data
    in the thread's private SQLite database.
    """
    return _build_workspace_tools_from_provider(lambda: workspace)


def _build_workspace_tools_from_provider(
    workspace_provider: Callable[[], ScopedWorkspace],
) -> tuple[BaseTool, ...]:
    """Build workspace tools that resolve the workspace lazily per call.

    Accepts a callable returning a ``ScopedWorkspace`` so that tools can
    be built once and reused across threads (e.g. in ``ReasonAdvancer``).
    """
    tool_from_function = _structured_tool_factory()

    def put(key: str, value: str, sub_namespace: str | None = None) -> str:
        """Store a JSON value under the given key in the thread's workspace."""
        import json as _json
        try:
            parsed = _json.loads(str(value))
        except _json.JSONDecodeError:
            return "Error: value must be a valid JSON string"
        if not isinstance(parsed, dict):
            return "Error: value must be a JSON object (dict)"
        workspace_provider().put(str(key), cast(dict[str, object], parsed), sub=str(sub_namespace) if sub_namespace else None)
        return f"Stored {key}"

    def get(key: str, sub_namespace: str | None = None) -> str:
        """Retrieve the JSON value stored under the given key."""
        import json as _json
        result = workspace_provider().get(str(key), sub=str(sub_namespace) if sub_namespace else None)
        if result is None:
            return f"Key {key} not found"
        return _json.dumps(result, ensure_ascii=True)

    def search(
        query: str | None = None,
        filter_json: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """Search items in the thread's workspace. Returns a JSON list."""
        import json as _json
        filter_dict: dict[str, object] | None = None
        if filter_json:
            try:
                parsed = _json.loads(str(filter_json))
                if isinstance(parsed, dict):
                    filter_dict = cast(dict[str, object], parsed)
            except _json.JSONDecodeError:
                return "Error: filter_json must be a valid JSON object"
        results = workspace_provider().search(
            query=str(query) if query else None,
            filter=filter_dict,
            limit=max(1, int(limit)),
            offset=max(0, int(offset)),
        )
        return _json.dumps(results, ensure_ascii=True)

    def delete(key: str, sub_namespace: str | None = None) -> str:
        """Delete an item from the thread's workspace."""
        workspace_provider().delete(str(key), sub=str(sub_namespace) if sub_namespace else None)
        return f"Deleted {key}"

    return (
        tool_from_function(put, name="workspace_put", description=put.__doc__ or "", metadata={"service_component": "workspace"}),
        tool_from_function(get, name="workspace_get", description=get.__doc__ or "", metadata={"service_component": "workspace"}),
        tool_from_function(search, name="workspace_search", description=search.__doc__ or "", metadata={"service_component": "workspace"}),
        tool_from_function(delete, name="workspace_delete", description=delete.__doc__ or "", metadata={"service_component": "workspace"}),
    )


def _structured_tool_factory() -> StructuredToolFactory:
    return cast(StructuredToolFactory, StructuredTool.from_function)  # pyright: ignore[reportUnknownMemberType]


def _json_result(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_error(message: str) -> str:
    return _json_result({"error": message})


def _reason_thread_payload(thread: ReasoningThread) -> dict[str, object]:
    return {
        "id": thread.id,
        "topic": thread.topic,
        "status": thread.status,
        "priority": thread.priority,
        "working_summary": thread.working_summary,
        "mandates": thread.mandates,
        "active_items": [item.to_wire() for item in thread.active_items],
        "pending_items": [item.to_wire() for item in thread.pending_items],
        "next_steps": [item.to_wire() for item in thread.next_steps],
        "reasoning_prompt": thread.reasoning_prompt,
        "evidence_refs": list(thread.evidence_refs),
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "last_advanced_at": thread.last_advanced_at,
        "next_review_after": thread.next_review_after,
        "skip_next_advance_until": thread.skip_next_advance_until,
    }


def _reason_step_payload(step: ReasoningStep, *, index: int) -> dict[str, object]:
    return {
        "index": index,
        "id": step.id,
        "thread_id": step.thread_id,
        "kind": step.kind,
        "summary": step.summary,
        "output": step.output,
        "delta": step.delta,
        "new_findings": [item.to_wire() for item in step.new_findings],
        "new_pending": [item.to_wire() for item in step.new_pending],
        "retired_findings": [item.to_wire() for item in step.retired_findings],
        "next_steps": [item.to_wire() for item in step.next_steps],
        "evidence_refs": list(step.evidence_refs),
        "confidence": step.confidence,
        "terminal_status": step.terminal_status,
        "terminal_reason": step.terminal_reason,
        "created_at": step.created_at,
    }


def _reason_show_payload(thread: ReasoningThread, steps: list[ReasoningStep]) -> dict[str, object]:
    return {
        "thread": _reason_thread_payload(thread),
        "step_count": len(steps),
        "steps": [_reason_step_payload(step, index=index) for index, step in enumerate(steps)],
        "tool_logs": "omitted",
    }


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
