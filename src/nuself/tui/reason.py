"""Terminal renderers for reasoning threads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from nuself.runtime.audit_types import LogComponent
from nuself.runtime.log_event import LogEvent
from nuself.reason.model import ReasoningStep, ReasoningThread, TrackedItem
from nuself.tui.render import (
    TerminalTheme,
    format_display_timestamp,
    render_key_value_field,
    render_log_event,
    render_markdown,
    render_record_block,
    render_record_header,
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
    include_tool_logs: bool = True,
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
    lines.append(f"  {theme.tag('description:', 'reasoning')}")
    if thread.working_summary:
        lines.append(f"    {render_markdown(thread.working_summary, theme)}")
    else:
        lines.append(f"    {theme.muted('(empty)')}")
    lines.append(f"  {theme.tag('mandates:', 'reasoning')}")
    if thread.mandates:
        for m in thread.mandates:
            lines.append(f"    - {m}")
    else:
        lines.append(f"    {theme.muted('(none)')}")
    _append_tracked_section(lines, "active_items", thread.active_items, theme)
    _append_tracked_section(lines, "pending_items", thread.pending_items, theme)
    _append_tracked_section(lines, "next_steps", thread.next_steps, theme)
    lines.append(f"  {theme.tag('reasoning_prompt:', 'reasoning')}")
    if thread.reasoning_prompt:
        for line in thread.reasoning_prompt.splitlines():
            lines.append(f"    {line}")
    else:
        lines.append(f"    {theme.muted('(not generated)')}")
    lines.append(f"  {theme.tag('evidence:', 'reasoning')}")
    if thread.evidence_refs:
        for r in thread.evidence_refs:
            lines.append(f"    - {r}")
    else:
        lines.append(f"    {theme.muted('(none)')}")
    if steps:
        lines.append("")
        for i, step in enumerate(steps):
            if i > 0:
                lines.append("")
            step_header = f"[{i + 1}] " if len(steps) > 1 else ""
            lines.append(
                _render_step_body(
                    step,
                    theme,
                    indent=0,
                    full=full,
                    step_prefix=step_header,
                    include_tool_logs=include_tool_logs,
                )
            )
    return "\n".join(lines)


def render_step_watch_entry(step: ReasoningStep, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    return _render_step_body(step, theme, indent=0, full=True, include_tool_logs=True)



 

def _render_step_body(
    step: ReasoningStep,
    theme: TerminalTheme,
    *,
    indent: int,
    full: bool = False,
    step_prefix: str = "",
    include_tool_logs: bool = True,
) -> str:
    pad = " " * indent
    kind_tag = theme.paint(f"[{step.kind}]", _step_kind_color(step.kind))
    ts = theme.muted(f"({format_display_timestamp(step.created_at)})")
    lines = [f"{pad}{step_prefix}{kind_tag} {ts}"]
    body_pad = f"{pad}  "
    if step.summary:
        lines.append(f"{body_pad}{render_markdown(step.summary, theme)}")
    if step.output:
        lines.append(f"{body_pad}{theme.tag('output:', 'reasoning')}")
        for line in step.output.splitlines():
            lines.append(f"{body_pad}  {render_markdown(line, theme)}")
    if include_tool_logs and step.tool_logs:
        for entry in step.tool_logs:
            inner_pad = " " * (indent + _TOOL_CALL_INDENT)
            log_event = LogEvent(
                time=step.created_at,
                level="info",
                component=cast(LogComponent, str(entry.get("component", "reasoning"))),
                event=str(entry.get("event", "")),
                message=str(entry.get("message", "")),
                status=str(entry.get("status")) if entry.get("status") else None,
                metadata=cast(dict[str, object] | None, entry.get("metadata")),
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
    if full or step.terminal_status != "continue":
        status_text = step.terminal_status
        if step.terminal_reason:
            status_text = f"{status_text} — {step.terminal_reason}"
        lines.append(f"{body_pad}{theme.tag('terminal:', 'reasoning')} {status_text}")
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
    items: Sequence[str],
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


def _append_tracked_section(
    lines: list[str],
    tag: str,
    items: list[TrackedItem],
    theme: TerminalTheme,
) -> None:
    lines.append(f"  {theme.tag(f'{tag}:', 'reasoning')}")
    if items:
        for item in items:
            suffix = f" ({item.kind})" if item.kind else ""
            description = f" — {item.description}" if item.description else ""
            lines.append(f"    - {item.label}{description}{suffix}")
    else:
        lines.append(f"    {theme.muted('(none)')}")


def _reason_status_color(status: str) -> str:
    return {"active": "32", "paused": "33", "resolved": "36", "archived": "90"}.get(status, "0")


def _step_kind_color(kind: str) -> str:
    return {"progress": "32", "no_change": "90", "question": "33", "synthesis": "35", "contradiction": "31", "resolution": "36"}.get(kind, "0")


def _maybe_muted(value: str, theme: TerminalTheme) -> str:
    return theme.muted(value) if theme.color else value
