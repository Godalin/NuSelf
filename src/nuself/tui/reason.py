"""Terminal renderers for reasoning threads."""

from __future__ import annotations

from nuself.agent.tool_utils import format_tool_debug_body
from nuself.logs import LogEvent
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.tui.render import (
    TerminalTheme,
    format_display_timestamp,
    render_key_value_field,
    render_log_event,
    render_markdown,
    render_record_block,
    render_record_header,
    render_section,
)

_TOOL_CALL_INDENT = 2
 


def render_reason_row(
    thread: ReasoningThread,
    *,
    index: int | None = None,
    color: bool | None = None,
) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag("[reason]", "reasoning")
    label = f"[{index}] {tag}" if index is not None else tag
    status_tag = theme.paint(f"[{thread.status}]", _reason_status_color(thread.status))
    fields = [
        render_key_value_field("status", status_tag),
        render_key_value_field("priority", thread.priority),
    ]
    if thread.last_advanced_at is not None:
        fields.append(theme.muted(render_key_value_field("advanced", format_display_timestamp(thread.last_advanced_at))))
    return render_record_block(label, fields, body=thread.topic)


def render_reason_detail(
    thread: ReasoningThread,
    steps: list[ReasoningStep] | None = None,
    *,
    color: bool | None = None,
    full: bool = False,
) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag("[reason]", "reasoning")
    status_tag = theme.paint(f"[{thread.status}]", _reason_status_color(thread.status))
    fields = [
        render_key_value_field("id", _maybe_muted(thread.id, theme)),
        render_key_value_field("status", status_tag),
        render_key_value_field("priority", thread.priority),
        render_key_value_field("created_at", _maybe_muted(thread.created_at, theme)),
    ]
    if thread.last_advanced_at is not None:
        fields.append(theme.muted(render_key_value_field("last_advanced_at", thread.last_advanced_at)))
    lines = [render_record_header(f"{tag} {thread.topic}", fields)]
    lines.extend(render_section("description", [thread.working_summary] if thread.working_summary else [], theme))
    mandates = thread.mandates
    if mandates:
        lines.extend(render_section("mandates", mandates, theme))
    active = thread.active_items
    if active:
        lines.extend(render_section("active_items", [f"{i.label}{' — ' + i.description if i.description else ''}{' (' + i.kind + ')' if i.kind else ''}" for i in active], theme))
    pending = thread.pending_items
    if pending:
        lines.extend(render_section("pending_items", [f"{i.label}{' — ' + i.description if i.description else ''}{' (' + i.kind + ')' if i.kind else ''}" for i in pending], theme))
    steps_list = thread.next_steps
    if steps_list:
        lines.extend(render_section("next_steps", [s.label for s in steps_list], theme))
    lines.extend(render_section("evidence", thread.evidence_refs, theme))
    if steps:
        lines.append("")
        for i, step in enumerate(steps):
            if i > 0:
                lines.append("")
            lines.append(_render_step_body(step, theme, indent=0, full=full))
    return "\n".join(lines)


def render_step_watch_entry(step: ReasoningStep, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    return _render_step_body(step, theme, indent=0, full=True)



 

def _render_step_body(
    step: ReasoningStep,
    theme: TerminalTheme,
    *,
    indent: int,
    full: bool = False,
) -> str:
    pad = " " * indent
    kind_tag = theme.paint(f"[{step.kind}]", _step_kind_color(step.kind))
    ts = theme.muted(f"({format_display_timestamp(step.created_at)})")
    lines = [f"{pad}{kind_tag} {ts}"]
    body_pad = f"{pad}  "
    if step.summary:
        lines.append(f"{body_pad}{render_markdown(step.summary, theme)}")
    if step.output:
        lines.append(f"{body_pad}{theme.tag('output:', 'reasoning')} {step.output}")
    if step.tool_calls:
        for name, service, args_dict, tc_result in step.tool_calls:
            if not service:
                continue
            inner_pad = " " * (indent + _TOOL_CALL_INDENT)
            body = format_tool_debug_body(args=args_dict, result=tc_result, full=True)
            log_event = LogEvent(
                time=step.created_at,
                level="info",
                component="reasoning",
                event="service_tool_called",
                message=body,
                status="completed",
                metadata={"service_component": service, "tool": name},
            )
            rendered = render_log_event(log_event, color=theme.color)
            for line in rendered.splitlines():
                lines.append(f"{inner_pad}{line}" if line else inner_pad.rstrip())
    _append_field(lines, body_pad, "delta", step.delta, theme, full=full)
    findings = step.new_findings
    if findings:
        _append_multi_field(lines, body_pad, "new_findings", [f"{f.label}{' — ' + f.description if f.description else ''}{' (' + f.kind + ')' if f.kind else ''}" for f in findings], theme, full=full)
    pending = step.new_pending
    if pending:
        _append_multi_field(lines, body_pad, "new_pending", [f"{p.label}{' — ' + p.description if p.description else ''}{' (' + p.kind + ')' if p.kind else ''}" for p in pending], theme, full=full)
    retired = step.retired_findings
    if retired:
        _append_multi_field(lines, body_pad, "retired_findings", [f"{r.label}{' — ' + r.description if r.description else ''}{' (' + r.kind + ')' if r.kind else ''}" for r in retired], theme, full=full)
    nxt = step.next_steps
    if nxt:
        _append_multi_field(lines, body_pad, "next_steps", [s.label for s in nxt], theme, full=full)
    _append_multi_field(lines, body_pad, "evidence_refs", step.evidence_refs, theme, full=full)
    if full or step.confidence is not None:
        conf = step.confidence
        if conf is not None:
            lines.append(f"{body_pad}{theme.tag('confidence:', 'reasoning')} {conf}")
        elif full:
            lines.append(f"{body_pad}{theme.tag('confidence:', 'reasoning')} {theme.muted('(none)')}")
    return "\n".join(lines)


def _append_field(
    lines: list[str],
    pad: str,
    tag: str,
    value: str | None,
    theme: TerminalTheme,
    *,
    full: bool,
) -> None:
    if value:
        lines.append(f"{pad}{theme.tag(f'{tag}:', 'reasoning')}")
        body_pad = pad + "  "
        for line in value.splitlines():
            rendered = render_markdown(line, theme) if line.strip() else ""
            lines.append(f"{body_pad}{rendered}")
    elif full:
        lines.append(f"{pad}{theme.tag(f'{tag}:', 'reasoning')} {theme.muted('(none)')}")


def _append_multi_field(
    lines: list[str],
    pad: str,
    tag: str,
    items: tuple[str, ...] | list[str],
    theme: TerminalTheme,
    *,
    full: bool,
) -> None:
    if items:
        lines.append(f"{pad}{theme.tag(f'{tag}:', 'reasoning')}")
        for item in items:
            lines.append(f"{pad}  - {render_markdown(item, theme)}")
    elif full:
        lines.append(f"{pad}{theme.tag(f'{tag}:', 'reasoning')} {theme.muted('(none)')}")


def _reason_status_color(status: str) -> str:
    return {"active": "32", "paused": "33", "resolved": "36", "archived": "90"}.get(status, "0")


def _step_kind_color(kind: str) -> str:
    return {"progress": "32", "no_change": "90", "question": "33", "synthesis": "35", "contradiction": "31", "resolution": "36"}.get(kind, "0")


def _maybe_muted(value: str, theme: TerminalTheme) -> str:
    return theme.muted(value) if theme.color else value
