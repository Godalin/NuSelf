"""One-shot dynamic Persona command adapters."""

from __future__ import annotations

import argparse

from nuself.cli.output import print_ansi
from nuself.cli.application import cli_application
from nuself.cli.persona_management import (
    create_persona,
    delete_personas,
    list_persona_prompts,
    resolve_persona_id,
    set_persona_enabled,
)
from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    MODERATOR_PERSONA,
    SYNTHESIZER_PERSONA,
)
from nuself.tui.persona import render_persona_detail, render_persona_row
from nuself.tui.render import TerminalTheme

_theme = TerminalTheme()


def handle_persona_list(args: argparse.Namespace) -> int:
    static = list(BUILTIN_PERSONAS) + [
        MODERATOR_PERSONA,
        SYNTHESIZER_PERSONA,
    ]
    lines = [
        f"{_theme.tag('[persona]', 'persona')} "
        "Built-in personas (static):"
    ]
    for persona in static:
        lines.append(
            f"  {_theme.muted(persona.id)}: {persona.description}"
        )
    prompts = list_persona_prompts(args.project_root)
    if prompts:
        lines.extend(
            (
                "",
                f"{_theme.tag('[persona]', 'persona')} "
                "Custom personas (dynamic):",
            )
        )
        for index, prompt in enumerate(prompts):
            lines.append(render_persona_row(prompt, index=index))
    else:
        empty_hint = (
            "(no custom personas yet — use persona_craft in chat "
            "to create one)"
        )
        lines.append(f"  {_theme.muted(empty_hint)}")
    print_ansi("\n".join(lines))
    return 0


def handle_persona_create(args: argparse.Namespace) -> int:
    return create_persona(args.project_root, args.name, args.prompt)


def handle_persona_show(args: argparse.Namespace) -> int:
    service = cli_application().personas
    prompt_id = resolve_persona_id(args.project_root, args.persona_id)
    if prompt_id is None:
        return 1
    prompt = service.get(prompt_id)
    if prompt is None:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} "
            f"{_theme.error(f'Persona not found: {args.persona_id}')}"
        )
        return 1
    print_ansi(render_persona_detail(prompt))
    return 0


def handle_persona_delete(args: argparse.Namespace) -> int:
    return delete_personas(
        args.project_root,
        args.persona_id,
        confirmed=args.yes,
    )


def handle_persona_disable(args: argparse.Namespace) -> int:
    return set_persona_enabled(
        args.project_root,
        args.persona_id,
        enabled=False,
        confirmed=args.yes,
    )


def handle_persona_enable(args: argparse.Namespace) -> int:
    return set_persona_enabled(
        args.project_root,
        args.persona_id,
        enabled=True,
        confirmed=args.yes,
    )
