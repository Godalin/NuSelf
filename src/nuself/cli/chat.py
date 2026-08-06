"""CLI adapters for daemon-backed and one-shot chat."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from nuself.agent.chat.composition import compose_conversation_runtime
from nuself.agent.chat.engine import ConversationGraphRuntime
from nuself.application.projection import publish_chat_observation
from nuself.cli.application import cli_application
from nuself.agent.chat.audit import (
    CHAT_AUDIT,
)
from nuself.cli.output import print_ansi
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.repl.types import InteractiveChatResult
from nuself.daemon import client
from nuself.daemon.payloads import ChatToolEffectPayload
from nuself.memory.audit import MEMORY_AUDIT
from nuself.runtime.context import runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.execution import current_cancellation
from nuself.tui.render import TerminalTheme
from nuself.tui.effect import TerminalToolEffectPort
from nuself.runtime.feature.protocol import ToolEffectResolution

type ReplyPrinter = Callable[[str], None]

_theme = TerminalTheme()


def send_daemon_chat(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Send one daemon-backed message and present its one-shot result."""

    turn_id = f"turn-{uuid4().hex}"
    effect_resolution: ToolEffectResolution | None = None
    while True:
        result = send_daemon_chat_interactive(
            message,
            project_root,
            conversation_id,
            turn_id=turn_id,
            effect_resolution=effect_resolution,
        )
        request = result.tool_effect_request
        if request is None:
            break
        effect_resolution = TerminalToolEffectPort().resolve(
            request,
            on_requested=lambda: None,
        )
    if result.reply is not None:
        print_reply(result.reply)
    if result.error is not None:
        print(result.error, file=sys.stderr)
    return result.code


def send_daemon_chat_interactive(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    turn_id: str | None = None,
    effect_resolution: ToolEffectResolution | None = None,
) -> InteractiveChatResult:
    """Translate one typed daemon chat operation to the REPL result contract."""

    with runtime_context(
        conversation_id=conversation_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            response = client.chat(
                message,
                conversation_id=conversation_id,
                turn_id=turn_id,
                project_root=project_root,
                timeout=(
                    cli_application()
                    .config.chat.request_timeout_seconds
                ),
                effect_resolution=effect_resolution,
            )
        except client.DaemonConnectionError as exc:
            cancellation = current_cancellation()
            if cancellation is not None and cancellation.cancelled:
                return InteractiveChatResult(
                    code=CliExitCode.INTERRUPTED,
                )
            error = (
                "daemon request failed: "
                f"{diagnostic_exception_message(exc)}"
            )
            print(error, file=sys.stderr)
            return InteractiveChatResult(
                code=(
                    CliExitCode.TEMPORARY_FAILURE
                    if exc.retryable
                    else CliExitCode.FAILURE
                ),
                retryable=exc.retryable,
                error=error,
                failure_phase=exc.phase,
                request_id=exc.request_id,
                request_may_have_completed=(
                    exc.request_may_have_completed
                ),
            )
        except client.DaemonApplicationError as exc:
            error = diagnostic_exception_message(exc)
            CHAT_AUDIT.failure(
                exc,
                event="daemon_chat_failed",
                project_root=project_root,
            )
            return InteractiveChatResult(
                code=CliExitCode.FAILURE,
                error=error,
            )
        if isinstance(response, ChatToolEffectPayload):
            return InteractiveChatResult(
                code=CliExitCode.SUCCESS,
                tool_effect_request=response.request,
            )
        with runtime_context(conversation_id=response.conversation_id):
            CHAT_AUDIT.write(
                "daemon_chat_completed",
                project_root=project_root,
            )
        return InteractiveChatResult(
            code=CliExitCode.SUCCESS,
            reply=response.answer,
        )

def send_one_shot_chat(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Run one local message and present its one-shot result."""

    result = send_one_shot_chat_interactive(
        message,
        project_root,
        conversation_id,
    )
    if result.reply is not None:
        print_reply(result.reply)
        if result.after_reply is not None:
            result.after_reply()
    return result.code


def send_one_shot_chat_interactive(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    turn_id: str | None = None,
    effect_resolution: ToolEffectResolution | None = None,
) -> InteractiveChatResult:
    """Run one local chat operation and translate expected runtime failure."""

    if effect_resolution is not None:
        raise RuntimeError(
            "one-shot Chat has no suspended Tool effect checkpoint"
        )
    with runtime_context(
        conversation_id=conversation_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            application = cli_application()
            conversation_runtime = compose_conversation_runtime(
                application.paths,
                application.config,
                application.conversations,
                application.memory,
                application.sources,
                application.reflection,
                application.reason,
                application.trace,
                application.personas,
                effect_port=TerminalToolEffectPort(),
            )
            result = conversation_runtime.respond(
                message,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
            application = cli_application()
            observation = publish_chat_observation(
                application.memory_workflows,
                turn=result.require_completed_turn(),
                source_trace_id=result.trace_id,
            )
            CHAT_AUDIT.write(
                "one_shot_chat_completed",
                project_root=project_root,
            )
            run_memory_curator(project_root, observation.id)
            return InteractiveChatResult(
                code=CliExitCode.SUCCESS,
                reply=result.answer,
                after_reply=lambda: _compress_after_reply(
                    conversation_runtime,
                    conversation_id,
                    project_root,
                ),
            )
        except RuntimeError as exc:
            error = diagnostic_exception_message(exc)
            CHAT_AUDIT.failure(
                exc,
                event="one_shot_chat_failed",
                project_root=project_root,
            )
            print(error, file=sys.stderr)
            return InteractiveChatResult(code=CliExitCode.FAILURE)


def run_memory_curator(
    project_root: Path | None,
    observation_id: str,
) -> None:
    """Run post-turn curation and present its optional status."""

    try:
        application = cli_application()
        result = application.memory_workflows.curator(
            application.trace.recorder,
            application.config,
        ).run_once(observation_id)
    except RuntimeError as exc:
        error = diagnostic_exception_message(exc)
        MEMORY_AUDIT.failure(
            exc,
            event="curator_failed",
            project_root=project_root,
        )
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} curator failed: {error}",
            file=sys.stderr,
        )
        return
    if result.changed:
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} {result.summary()}"
        )


def _compress_after_reply(
    conversation_runtime: ConversationGraphRuntime,
    conversation_id: str,
    project_root: Path | None,
) -> None:
    try:
        conversation_runtime.compress_conversation(conversation_id)
    except Exception as exc:
        CHAT_AUDIT.failure(
            exc,
            event="compression_fallback",
            project_root=project_root,
        )
