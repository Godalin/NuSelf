"""Terminal renderers for trace records."""

from __future__ import annotations

from nuself.trace.domain import ThoughtTrace, TraceLink
from nuself.tui.render import (
    TerminalTheme,
    format_display_timestamp,
    render_key_value_field,
    render_record_block,
    render_record_header,
    render_section,
)


def render_trace_row(trace: ThoughtTrace, *, index: int | None = None, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag("[trace]", "trace")
    label = f"[{index}] {tag}" if index is not None else tag
    fields = [
        render_key_value_field("kind", trace.kind),
        render_key_value_field("visibility", trace.visibility),
        render_key_value_field("created", format_display_timestamp(trace.created_at)),
    ]
    if trace.thread_id is not None:
        fields.append(render_key_value_field("thread", trace.thread_id))
    return render_record_block(label, fields, body=trace.title)


def render_trace_detail(trace: ThoughtTrace, links: list[TraceLink] | None = None, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag("[trace]", "trace")
    fields = [
        render_key_value_field("id", trace.id),
        render_key_value_field("kind", trace.kind),
        render_key_value_field("visibility", trace.visibility),
        render_key_value_field("created_at", trace.created_at),
    ]
    if trace.thread_id is not None:
        fields.append(render_key_value_field("thread", trace.thread_id))
    lines = [render_record_header(f"{tag} {trace.title}", fields)]
    lines.extend(render_section("summary", [trace.summary], theme))
    lines.extend(render_section("inputs", trace.inputs, theme))
    lines.extend(render_section("evidence", trace.evidence_refs, theme))
    lines.extend(render_section("derived_from", trace.derived_from, theme))
    lines.extend(render_section("outputs", trace.outputs, theme))
    lines.extend(render_section("participants", trace.participants, theme))
    lines.extend(render_section("decision_points", trace.decision_points, theme))
    if links:
        rendered_links = [
            f"{link.relation}: {link.source_id} -> {link.target_id} ({link.summary})"
            for link in links
        ]
        lines.extend(render_section("links", rendered_links, theme))
    return "\n".join(lines)
