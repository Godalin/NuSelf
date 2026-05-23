"""Terminal renderers for reasoning threads."""

from __future__ import annotations

from nuself.agent.tool_utils import format_tool_debug_body
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.tui.render import (
    TerminalTheme,
    format_display_timestamp,
    render_key_value_field,
    render_record_block,
    render_record_header,
    render_tool_call,
)

_TOOL_CALL_INDENT = 2


def _render_markdown(text: str, theme: TerminalTheme) -> str:
    """Render markdown text to ANSI-formatted string if color is enabled."""
    if not theme.color:
        return text
    from rich.console import Console
    from rich.markdown import Markdown
    import io
    buf = io.StringIO()
    Console(file=buf, force_terminal=True, width=160).print(Markdown(text), end="")
    return buf.getvalue().rstrip()


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
    lines = [render_record_header(f"{tag} {thread.question}", fields)]
    lines.extend(_section("summary", [thread.working_summary] if thread.working_summary else [], theme))
    lines.extend(_section("hypotheses", thread.hypotheses, theme))
    lines.extend(_section("open_questions", thread.open_questions, theme))
    lines.extend(_section("evidence", thread.evidence_refs, theme))
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


def _tool_service_tag(name: str) -> str:
    """Extract the service component tag from a tool name."""
    if name.startswith("memory_"):
        return "memory"
    if name.startswith("reflection_"):
        return "reflection"
    if name.startswith("reason_"):
        return "reasoning"
    if name.startswith("trace_"):
        return "trace"
    if name.startswith("selves_"):
        return "selves"
    if name == "load_skill":
        return "skill"
    return ""
 



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
        lines.append(f"{body_pad}{_render_markdown(step.summary, theme)}")
    if step.tool_calls:
        for name, args_dict, tc_result in step.tool_calls:
            service_tag = _tool_service_tag(name)
            if not service_tag:
                continue
            inner_pad = " " * (indent + _TOOL_CALL_INDENT)
            tc_rendered = render_tool_call(
                component="reasoning",
                service=service_tag,
                args_text=format_tool_debug_body(args=args_dict, result=tc_result, full=True),
                status="completed",
                color=theme.color,
            )
            for line in tc_rendered.splitlines():
                lines.append(f"{inner_pad}{line}" if line else inner_pad.rstrip())
    _append_field(lines, body_pad, "delta", step.delta, theme, full=full)
    _append_multi_field(lines, body_pad, "new_hypotheses", step.new_hypotheses, theme, full=full)
    _append_multi_field(lines, body_pad, "new_open_questions", step.new_open_questions, theme, full=full)
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
            rendered = _render_markdown(line, theme) if line.strip() else ""
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
            lines.append(f"{pad}  - {_render_markdown(item, theme)}")
    elif full:
        lines.append(f"{pad}{theme.tag(f'{tag}:', 'reasoning')} {theme.muted('(none)')}")


def _reason_status_color(status: str) -> str:
    return {"active": "32", "paused": "33", "resolved": "36", "archived": "90"}.get(status, "0")


def _step_kind_color(kind: str) -> str:
    return {"progress": "32", "no_change": "90", "question": "33", "synthesis": "35", "contradiction": "31", "resolution": "36"}.get(kind, "0")


def _maybe_muted(value: str, theme: TerminalTheme) -> str:
    return theme.muted(value) if theme.color else value


def _section(title: str, values: list[str], theme: TerminalTheme) -> list[str]:
    if not values:
        return []
    label = theme.tag(f"{title}:", "reasoning")
    lines = [f"  {label}"]
    lines.extend(f"    - {_render_markdown(value, theme)}" for value in values)
    return lines
