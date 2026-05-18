"""Terminal renderers for reasoning threads."""

from __future__ import annotations

from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.tui.render import format_display_timestamp, render_key_value_field, render_record_block, render_record_header


def render_reason_row(thread: ReasoningThread, *, index: int | None = None) -> str:
    label = f"[{index}] [reason]" if index is not None else "[reason]"
    fields = [
        render_key_value_field("status", thread.status),
        render_key_value_field("priority", thread.priority),
    ]
    if thread.last_advanced_at is not None:
        fields.append(render_key_value_field("advanced", format_display_timestamp(thread.last_advanced_at)))
    return render_record_block(label, fields, body=thread.question)


def render_reason_detail(thread: ReasoningThread, steps: list[ReasoningStep] | None = None) -> str:
    fields = [
        render_key_value_field("id", thread.id),
        render_key_value_field("status", thread.status),
        render_key_value_field("priority", thread.priority),
        render_key_value_field("created_at", thread.created_at),
    ]
    if thread.last_advanced_at is not None:
        fields.append(render_key_value_field("last_advanced_at", thread.last_advanced_at))
    lines = [render_record_header(f"[reason] {thread.question}", fields)]
    lines.extend(_section("summary", [thread.working_summary] if thread.working_summary else []))
    lines.extend(_section("hypotheses", thread.hypotheses))
    lines.extend(_section("open_questions", thread.open_questions))
    lines.extend(_section("evidence", thread.evidence_refs))
    if steps:
        lines.append("")
        lines.append("  steps:")
        for step in steps:
            lines.append(f"    [{step.kind}] {step.summary}")
    return "\n".join(lines)


def _section(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    lines = [f"  {title}:"]
    lines.extend(f"    - {value}" for value in values)
    return lines
