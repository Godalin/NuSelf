"""One-shot dynamic persona command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path

from nuself.application import compose_trace_services
from nuself.cli.commands.output import (
    print_ansi,
    resolve_handle,
    resolve_handle_selection,
)
from nuself.cli.composition import compose_cli_application
from nuself.cli.control import ConfirmationDecision, read_confirmation
from nuself.cli.exit_codes import CliExitCode
from nuself.config import runtime_paths
from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    MODERATOR_PERSONA,
    SYNTHESIZER_PERSONA,
)
from nuself.persona.prompt_repo import (
    PersonaPrompt,
    create_persona_prompt,
)
from nuself.persona.audit import run_persona_observed
from nuself.storage import get_default_backend
from nuself.tui.persona import render_persona_detail, render_persona_row
from nuself.tui.render import TerminalTheme

_theme = TerminalTheme()


def _prompts_for_list(
    project_root: Path | None,
) -> tuple[PersonaPrompt, ...]:
    return compose_cli_application(project_root).persona_prompts.list()


def resolve_persona_id(args: argparse.Namespace) -> str | None:
    return resolve_handle(
        args.persona_id,
        _prompts_for_list(args.project_root),
        label="persona",
        get_id=lambda prompt: prompt.id,
    )


def resolve_persona_ids(
    args: argparse.Namespace,
) -> list[str] | None:
    return resolve_handle_selection(
        args.persona_id,
        _prompts_for_list(args.project_root),
        label="persona",
        get_id=lambda prompt: prompt.id,
    )


def _record_lifecycle(
    project_root: Path | None,
    *,
    action: str,
    persona: PersonaPrompt,
) -> None:
    recorder = compose_trace_services(
        runtime_paths(project_root),
        get_default_backend(project_root),
    ).recorder
    method = getattr(recorder, f"record_persona_{action}")

    def record() -> object:
        return method(
            persona_prompt_id=persona.id,
            name=persona.name,
            participants=["cli"],
        )

    run_persona_observed(
        record,
        event="trace_recording_failed",
        project_root=project_root,
        metadata={
            "persona_prompt_id": persona.id,
            "action": action,
        },
        errors=(RuntimeError,),
    )


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
    prompts = _prompts_for_list(args.project_root)
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
        lines.append(
            f"  {_theme.muted(empty_hint)}"
        )
    print_ansi("\n".join(lines))
    return 0


def handle_persona_create(args: argparse.Namespace) -> int:
    repository = compose_cli_application(args.project_root).persona_prompts
    persona = create_persona_prompt(args.name, args.prompt)
    existing = repository.get_by_name(args.name)
    if existing is not None:
        persona = PersonaPrompt(
            id=existing.id,
            name=args.name,
            prompt=args.prompt,
            disabled=existing.disabled,
            created_at=existing.created_at,
            updated_at=persona.updated_at,
        )
    repository.save(persona)
    _record_lifecycle(
        args.project_root, action="prompt_created", persona=persona
    )
    print_ansi(
        f"{_theme.tag('[persona]', 'persona')} "
        f"{_theme.paint(f'Created: {persona.name}', '32')} "
        f"(id={_theme.muted(persona.id)})"
    )
    return 0


def handle_persona_show(args: argparse.Namespace) -> int:
    repository = compose_cli_application(args.project_root).persona_prompts
    prompt_id = resolve_persona_id(args)
    if prompt_id is None:
        return 1
    prompt = repository.get(prompt_id)
    if prompt is None:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} "
            f"{_theme.error(f'Persona not found: {args.persona_id}')}"
        )
        return 1
    print_ansi(render_persona_detail(prompt))
    return 0


def handle_persona_delete(args: argparse.Namespace) -> int:
    repository = compose_cli_application(args.project_root).persona_prompts
    prompt_ids = resolve_persona_ids(args)
    if prompt_ids is None:
        return 1
    if not args.yes:
        names = [
            prompt.name
            for prompt in (
                repository.get(prompt_id) for prompt_id in prompt_ids
            )
            if prompt is not None
        ]
        if not names:
            return 1
        decision = read_confirmation(
            f"Delete persona(s): {', '.join(names)}? [y/N] "
        )
        if decision is ConfirmationDecision.INTERRUPTED:
            return CliExitCode.INTERRUPTED
        if decision is ConfirmationDecision.NO:
            print("Aborted.")
            return CliExitCode.SUCCESS
    deleted: list[str] = []
    for prompt_id in prompt_ids:
        prompt = repository.get(prompt_id)
        if prompt is not None:
            repository.delete(prompt_id)
            deleted.append(prompt.name)
    for name in deleted:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} "
            f"{_theme.warning(f'Deleted: {name}')}"
        )
    return 0


def _set_enabled(
    args: argparse.Namespace, *, enabled: bool
) -> int:
    repository = compose_cli_application(args.project_root).persona_prompts
    prompt_id = resolve_persona_id(args)
    if prompt_id is None:
        return 1
    prompt = repository.get(prompt_id)
    if prompt is None:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} "
            f"{_theme.error(f'Persona not found: {args.persona_id}')}"
        )
        return 1
    state = "enabled" if enabled else "disabled"
    if prompt.disabled is not enabled:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} Persona "
            f"'{prompt.name}' is already {_theme.muted(state)}."
        )
        return 0
    verb = "Enable" if enabled else "Disable"
    if not args.yes:
        decision = read_confirmation(
            f"{verb} persona '{prompt.name}'? [y/N] "
        )
        if decision is ConfirmationDecision.INTERRUPTED:
            return CliExitCode.INTERRUPTED
        if decision is ConfirmationDecision.NO:
            print("Aborted.")
            return CliExitCode.SUCCESS
    repository.set_disabled(prompt.id, not enabled)
    action = "enabled" if enabled else "disabled"
    _record_lifecycle(
        args.project_root, action=action, persona=prompt
    )
    rendered = (
        _theme.paint(f"Enabled: {prompt.name}", "32")
        if enabled
        else _theme.warning(f"Disabled: {prompt.name}")
    )
    print_ansi(f"{_theme.tag('[persona]', 'persona')} {rendered}")
    return 0


def handle_persona_disable(args: argparse.Namespace) -> int:
    return _set_enabled(args, enabled=False)


def handle_persona_enable(args: argparse.Namespace) -> int:
    return _set_enabled(args, enabled=True)
