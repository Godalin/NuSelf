"""Terminal renderers for persona prompts."""

from __future__ import annotations

from nuself.persona.prompt_repo import PersonaPrompt
from nuself.tui.render import (
    TerminalTheme,
    format_display_timestamp,
    render_record_block,
)

_DEFAULT_TEXT_WIDTH = 88


def _wrap_body(text: str) -> str:
    import shutil
    import textwrap

    width = shutil.get_terminal_size((_DEFAULT_TEXT_WIDTH, 24)).columns
    lines = textwrap.wrap(text, width=max(min(width, _DEFAULT_TEXT_WIDTH), 40)) or [""]
    return "\n".join(lines)


def render_persona_row(
    prompt: PersonaPrompt,
    *,
    index: int | None = None,
    color: bool | None = None,
) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag("[persona]", "persona")
    name = theme.paint(prompt.name, "38;5;208")
    label = f"{tag} [{index}] {name}" if index is not None else f"{tag} {name}"
    fields: list[str] = [f"id={theme.muted(prompt.id)}"]
    if prompt.disabled:
        fields.append(theme.muted("[disabled]"))
    return render_record_block(label, fields, body=_wrap_body(prompt.prompt))


def render_persona_detail(
    prompt: PersonaPrompt,
    *,
    color: bool | None = None,
) -> str:
    theme = TerminalTheme(color=color)
    fields: list[str] = [f"id={theme.muted(prompt.id)}"]
    fields.append(f"created={format_display_timestamp(prompt.created_at)}")
    fields.append(f"updated={format_display_timestamp(prompt.updated_at)}")
    if prompt.disabled:
        fields.append(theme.muted("[disabled]"))
    return render_record_block(
        f"{theme.tag('[persona]', 'persona')} {theme.paint(prompt.name, '38;5;208')}",
        fields,
        body=_wrap_body(prompt.prompt),
    )
