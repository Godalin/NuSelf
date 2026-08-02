"""Terminal workflows shared by one-shot and interactive Persona adapters."""

from __future__ import annotations

from pathlib import Path

from nuself.cli.output import (
    print_ansi,
    resolve_handle,
    resolve_handle_selection,
)
from nuself.cli.application import cli_application
from nuself.cli.control import ConfirmationDecision, read_confirmation
from nuself.cli.exit_codes import CliExitCode
from nuself.persona.audit import PERSONA_AUDIT
from nuself.persona.prompt_repo import PersonaPrompt, create_persona_prompt
from nuself.trace.service import TraceRecorder
from nuself.tui.render import TerminalTheme

_theme = TerminalTheme()


def list_persona_prompts(
    project_root: Path | None,
) -> tuple[PersonaPrompt, ...]:
    return cli_application().persona_prompts.list()


def resolve_persona_id(
    project_root: Path | None,
    persona_ref: str,
) -> str | None:
    return _resolve_persona_id(
        persona_ref,
        list_persona_prompts(project_root),
    )


def _resolve_persona_id(
    persona_ref: str,
    prompts: tuple[PersonaPrompt, ...],
) -> str | None:
    return resolve_handle(
        persona_ref,
        prompts,
        label="persona",
        get_id=lambda prompt: prompt.id,
    )


def _resolve_persona_ids(
    persona_ref: str,
    prompts: tuple[PersonaPrompt, ...],
) -> list[str] | None:
    return resolve_handle_selection(
        persona_ref,
        prompts,
        label="persona",
        get_id=lambda prompt: prompt.id,
    )


def create_persona(
    project_root: Path | None,
    name: str,
    prompt_text: str,
) -> int:
    application = cli_application()
    repository = application.persona_prompts
    persona = create_persona_prompt(name, prompt_text)
    existing = repository.get_by_name(name)
    if existing is not None:
        persona = PersonaPrompt(
            id=existing.id,
            name=name,
            prompt=prompt_text,
            disabled=existing.disabled,
            created_at=existing.created_at,
            updated_at=persona.updated_at,
        )
    repository.save(persona)
    _record_lifecycle(
        application.trace.recorder,
        project_root,
        action="prompt_created",
        persona=persona,
    )
    print_ansi(
        f"{_theme.tag('[persona]', 'persona')} "
        f"{_theme.paint(f'Created: {persona.name}', '32')} "
        f"(id={_theme.muted(persona.id)})"
    )
    return CliExitCode.SUCCESS


def delete_personas(
    project_root: Path | None,
    persona_ref: str,
    *,
    confirmed: bool = False,
) -> int:
    application = cli_application()
    repository = application.persona_prompts
    prompt_ids = _resolve_persona_ids(persona_ref, repository.list())
    if prompt_ids is None:
        return CliExitCode.FAILURE
    if not confirmed:
        names = [
            prompt.name
            for prompt in (
                repository.get(prompt_id) for prompt_id in prompt_ids
            )
            if prompt is not None
        ]
        if not names:
            return CliExitCode.FAILURE
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
    return CliExitCode.SUCCESS


def set_persona_enabled(
    project_root: Path | None,
    persona_ref: str,
    *,
    enabled: bool,
    confirmed: bool = False,
) -> int:
    application = cli_application()
    repository = application.persona_prompts
    prompt_id = _resolve_persona_id(persona_ref, repository.list())
    if prompt_id is None:
        return CliExitCode.FAILURE
    prompt = repository.get(prompt_id)
    if prompt is None:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} "
            f"{_theme.error(f'Persona not found: {persona_ref}')}"
        )
        return CliExitCode.FAILURE
    state = "enabled" if enabled else "disabled"
    if prompt.disabled is not enabled:
        print_ansi(
            f"{_theme.tag('[persona]', 'persona')} Persona "
            f"'{prompt.name}' is already {_theme.muted(state)}."
        )
        return CliExitCode.SUCCESS
    verb = "Enable" if enabled else "Disable"
    if not confirmed:
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
        application.trace.recorder,
        project_root,
        action=action,
        persona=prompt,
    )
    rendered = (
        _theme.paint(f"Enabled: {prompt.name}", "32")
        if enabled
        else _theme.warning(f"Disabled: {prompt.name}")
    )
    print_ansi(f"{_theme.tag('[persona]', 'persona')} {rendered}")
    return CliExitCode.SUCCESS


def _record_lifecycle(
    recorder: TraceRecorder,
    project_root: Path | None,
    *,
    action: str,
    persona: PersonaPrompt,
) -> None:
    method = getattr(recorder, f"record_persona_{action}")

    def record() -> object:
        return method(
            persona_prompt_id=persona.id,
            name=persona.name,
            participants=["cli"],
        )

    PERSONA_AUDIT.observe(
        record,
        event="trace_recording_failed",
        project_root=project_root,
        metadata={
            "persona_prompt_id": persona.id,
            "action": action,
        },
        errors=(RuntimeError,),
    )
