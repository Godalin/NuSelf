"""Trace-owned framework tool definitions."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.feature_execution import FeatureExecutor
from nuself.runtime import encode_json_value
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.trace.repository import TraceNotFound
from nuself.trace.service import TraceQueryService


def build_trace_tools(
    service: TraceQueryService,
    *,
    executor: FeatureExecutor | None = None,
) -> tuple[BaseTool, ...]:
    """Build the trace service's chat tools."""
    execution = executor or FeatureExecutor()

    @tool(
        name="trace_search",
        description=(
            "Search NuSelf thought provenance records. Use when the user asks where an idea came from, "
            "how a belief or answer formed, or what prior records support a conclusion."
        ),
    )
    @component("trace")
    @readonly
    @observed
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
        return encode_json_value(
            {"traces": [trace.to_wire() for trace in traces]},
            ensure_ascii=False,
            indent=2,
        )

    @tool(
        name="trace_count",
        description=(
            "Count thought provenance trace records, optionally matching a query. Use when the user asks "
            "how many provenance records exist or match a topic."
        ),
    )
    @component("trace")
    @readonly
    @observed
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

    @tool(
        name="trace_show",
        description=(
            "Show a specific thought provenance trace record with related "
            "links. Requires a trace_id."
        ),
    )
    @component("trace")
    @readonly
    @observed
    def show_trace(trace_id: str) -> str:
        """Show one thought provenance trace record."""
        if not trace_id.strip():
            return "Error: trace_id must be a non-empty string"
        try:
            trace = service.show_trace(trace_id.strip())
        except TraceNotFound as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return encode_json_value(
            {
                "trace": trace.to_wire(),
                "links": [
                    link.to_wire()
                    for link in service.links_for(trace.id)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    @tool(
        name="trace_related",
        description=(
            "List trace records and links that directly mention an artifact reference such as memory:<id>, "
            "reflection:<id>, reason:<id>, reason_step:<id>, persona_prompt:<id>, or trace:<id>."
        ),
    )
    @component("trace")
    @readonly
    @observed
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
        return encode_json_value(
            {
                "artifact_ref": artifact,
                "traces": [trace.to_wire() for trace in traces],
                "links": [link.to_wire() for link in links],
            },
            ensure_ascii=False,
            indent=2,
        )

    return (
        materialize_tool(search_trace, executor=execution),
        materialize_tool(count_traces, executor=execution),
        materialize_tool(show_trace, executor=execution),
        materialize_tool(related_traces, executor=execution),
    )
