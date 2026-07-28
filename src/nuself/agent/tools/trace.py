"""Trace-owned framework tool definitions."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from nuself.agent.tools.common import structured_tool_factory
from nuself.trace.repository import TraceNotFound
from nuself.trace.service import TraceQueryService
from nuself.tui.trace import render_trace_detail, render_trace_row


def build_trace_tools(
    service: TraceQueryService,
) -> tuple[BaseTool, ...]:
    """Build the trace service's chat tools."""
    tool_from_function = structured_tool_factory()

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
        traces = service.search_traces(query_str.strip())[:limit_int]
        if not traces:
            return f"No trace records matched: {query_str}"
        lines = ["Matching trace records:"]
        lines.extend(
            render_trace_row(trace, index=index, color=False)
            for index, trace in enumerate(traces)
        )
        return "\n".join(lines)

    def count_traces(query: str | None = None) -> str:
        """Count thought provenance trace records, optionally matching a query."""
        query_str = query.strip() if isinstance(query, str) else ""
        traces = (
            service.search_traces(query_str)
            if query_str
            else service.list_traces()
        )
        suffix = f' matching "{query_str}"' if query_str else ""
        return f"Trace records{suffix}: {len(traces)} total"

    def show_trace(trace_id: str) -> str:
        """Show one thought provenance trace record."""
        if not trace_id.strip():
            return "Error: trace_id must be a non-empty string"
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
        traces = service.traces_for_artifact(artifact)[:limit_int]
        links = service.links_for_artifact(artifact)
        if not traces and not links:
            return f"No trace records or links related to: {artifact}"
        lines = [f"Trace records related to {artifact}:"]
        lines.extend(
            render_trace_row(trace, index=index, color=False)
            for index, trace in enumerate(traces)
        )
        if links:
            lines.append("Related links:")
            lines.extend(
                f"  {link.relation}: {link.source_id} -> "
                f"{link.target_id} ({link.summary})"
                for link in links
            )
        return "\n".join(lines)

    return (
        tool_from_function(
            search_trace,
            name="trace_search",
            description=(
                "Search NuSelf thought provenance records. Use when the user asks where an idea came from, "
                "how a belief or answer formed, or what prior records support a conclusion."
            ),
            tags=("readonly",),
            metadata={"service_component": "trace"},
        ),
        tool_from_function(
            count_traces,
            name="trace_count",
            description=(
                "Count thought provenance trace records, optionally matching a query. Use when the user asks "
                "how many provenance records exist or match a topic."
            ),
            tags=("readonly",),
            metadata={"service_component": "trace"},
        ),
        tool_from_function(
            show_trace,
            name="trace_show",
            description=(
                "Show a specific thought provenance trace record with related "
                "links. Requires a trace_id."
            ),
            tags=("readonly",),
            metadata={"service_component": "trace"},
        ),
        tool_from_function(
            related_traces,
            name="trace_related",
            description=(
                "List trace records and links that directly mention an artifact reference such as memory:<id>, "
                "reflection:<id>, reason:<id>, reason_step:<id>, persona_prompt:<id>, or trace:<id>."
            ),
            tags=("readonly",),
            metadata={"service_component": "trace"},
        ),
    )
