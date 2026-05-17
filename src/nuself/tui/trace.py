"""Terminal renderers for trace records."""

from __future__ import annotations

from nuself.trace.domain import ThoughtTrace, TraceLink
from nuself.tui.render import format_display_timestamp, render_key_value_field, render_record_block, render_record_header


def render_trace_row(trace: ThoughtTrace, *, index: int | None = None) -> str:
    label = f"[{index}] [trace]" if index is not None else "[trace]"
    fields = [
        render_key_value_field("kind", trace.kind),
        render_key_value_field("visibility", trace.visibility),
        render_key_value_field("created", format_display_timestamp(trace.created_at)),
    ]
    if trace.thread_id is not None:
        fields.append(render_key_value_field("thread", trace.thread_id))
    return render_record_block(label, fields, body=trace.title)


def render_trace_detail(trace: ThoughtTrace, links: list[TraceLink] | None = None) -> str:
    fields = [
        render_key_value_field("id", trace.id),
        render_key_value_field("kind", trace.kind),
        render_key_value_field("visibility", trace.visibility),
        render_key_value_field("created_at", trace.created_at),
    ]
    if trace.thread_id is not None:
        fields.append(render_key_value_field("thread", trace.thread_id))
    lines = [render_record_header(f"[trace] {trace.title}", fields)]
    lines.extend(_section("summary", [trace.summary]))
    lines.extend(_section("inputs", trace.inputs))
    lines.extend(_section("evidence", trace.evidence_refs))
    lines.extend(_section("derived_from", trace.derived_from))
    lines.extend(_section("outputs", trace.outputs))
    lines.extend(_section("participants", trace.participants))
    lines.extend(_section("decision_points", trace.decision_points))
    if links:
        rendered_links = [
            f"{link.relation}: {link.source_id} -> {link.target_id} ({link.summary})"
            for link in links
        ]
        lines.extend(_section("links", rendered_links))
    return "\n".join(lines)


def _section(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    lines = [f"  {title}:"]
    lines.extend(f"    - {value}" for value in values)
    return lines
