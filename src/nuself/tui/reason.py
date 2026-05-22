"""Terminal renderers for reasoning threads."""

from __future__ import annotations

from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.tui.render import TerminalTheme, format_display_timestamp, render_key_value_field, render_record_block, render_record_header


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
    return render_record_block(label, fields, body=thread.question)


def render_reason_detail(
    thread: ReasoningThread,
    steps: list[ReasoningStep] | None = None,
    *,
    color: bool | None = None,
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
    lines = [render_record_header(f"{tag} {thread.question}", fields)]
    lines.extend(_section("summary", [thread.working_summary] if thread.working_summary else [], theme))
    lines.extend(_section("hypotheses", thread.hypotheses, theme))
    lines.extend(_section("open_questions", thread.open_questions, theme))
    lines.extend(_section("evidence", thread.evidence_refs, theme))
    if steps:
        lines.append("")
        lines.append(f"  {theme.tag('steps:', 'reasoning')}")
        for step in steps:
            kind_tag = theme.paint(f"[{step.kind}]", _step_kind_color(step.kind))
            lines.append(f"    {kind_tag} {step.summary}")
    return "\n".join(lines)


def render_step_watch_entry(step: ReasoningStep, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    kind_tag = theme.paint(f"[{step.kind}]", _step_kind_color(step.kind))
    ts = theme.muted(f"({format_display_timestamp(step.created_at)})")
    lines = [f"  {kind_tag} {step.summary}  {ts}"]
    if step.delta:
        lines.append(f"    {step.delta}")
    if step.new_hypotheses:
        lines.append(f"    {theme.tag('new hypotheses:', 'reasoning')}")
        for h in step.new_hypotheses:
            lines.append(f"      - {h}")
    return "\n".join(lines)


def _reason_status_color(status: str) -> str:
    if status == "active":
        return "32"
    if status == "paused":
        return "33"
    if status == "resolved":
        return "36"
    if status == "archived":
        return "90"
    return "0"


def _step_kind_color(kind: str) -> str:
    if kind == "progress":
        return "32"
    if kind == "no_change":
        return "90"
    if kind == "question":
        return "33"
    if kind == "synthesis":
        return "35"
    if kind == "contradiction":
        return "31"
    if kind == "resolution":
        return "36"
    return "0"


def _maybe_muted(value: str, theme: TerminalTheme) -> str:
    return theme.muted(value) if theme.color else value


def _section(title: str, values: list[str], theme: TerminalTheme) -> list[str]:
    if not values:
        return []
    label = theme.tag(f"{title}:", "reasoning")
    lines = [f"  {label}"]
    lines.extend(f"    - {value}" for value in values)
    return lines
