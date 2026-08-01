"""Composition of the interactive REPL callback graph."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nuself.cli.composition import compose_cli_application
from nuself.cli.daemon_status import observe_daemon_status
from nuself.cli.presentation import (
    brand_banner,
    print_assistant_reply,
    print_session_header,
)
from nuself.cli.repl.activity import (
    print_interactive_activity_events,
    read_interactive_activity_events,
)
from nuself.cli.repl.dispatcher import ReplCommandDispatcher
from nuself.cli.repl.notices import (
    print_interactive_notices,
    startup_interactive_notices,
)
from nuself.cli.repl.runtime import ReplCallbacks, run_interactive_loop
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.transcript import auto_save_interactive_transcripts
from nuself.cli.repl.turns import (
    send_interactive_chat_turn as _run_interactive_chat_turn,
)
from nuself.cli.repl.types import InteractiveChatResult

INTERACTIVE_CHAT_ATTEMPTS = 2
INTERACTIVE_LOG_POLL_INTERVAL_SECONDS = 0.1

MemoryCuratorRunner = Callable[[Path | None, str], object]


def run_repl(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    *,
    run_memory_curator: MemoryCuratorRunner,
    initial_conversation_id: str = "default",
    daemon_activity: bool = False,
) -> int:
    """Compose and run one interactive session."""
    command_dispatcher = ReplCommandDispatcher()

    def curate_session(
        root: Path | None,
        conversation_ids: tuple[str, ...],
    ) -> None:
        if daemon_activity:
            return
        del conversation_ids
        application = compose_cli_application(root)
        for observation in application.memory.observations.pending():
            run_memory_curator(root, observation.id)

    def send_turn(
        turn_sender: Callable[
            [str, str, str | None],
            InteractiveChatResult,
        ],
        turn_project_root: Path | None,
        conversation_id: str,
        message: str,
        session: InteractiveSession,
    ) -> int:
        return send_interactive_chat_turn(
            turn_sender,
            turn_project_root,
            conversation_id,
            message,
            session,
            daemon_activity=daemon_activity,
        )

    return run_interactive_loop(
        send_message,
        project_root,
        ReplCallbacks(
            handle_command=command_dispatcher.handle,
            send_turn=send_turn,
            auto_save=auto_save_interactive_transcripts,
            run_curator=curate_session,
            show_session_header=lambda root, conversation_id: (
                print_session_header(
                    interactive_daemon_status(root),
                    conversation_id,
                )
            ),
            show_startup_notices=lambda root: print_interactive_notices(
                startup_interactive_notices(root)
            ),
            brand_banner=brand_banner,
        ),
        initial_conversation_id=initial_conversation_id,
    )


def send_interactive_chat_turn(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    conversation_id: str,
    message: str,
    session: InteractiveSession,
    *,
    daemon_activity: bool = False,
) -> int:
    """Run one interactive turn with the shared activity policy."""
    return _run_interactive_chat_turn(
        send_message,
        project_root,
        conversation_id,
        message,
        session,
        daemon_activity=daemon_activity,
        max_attempts=INTERACTIVE_CHAT_ATTEMPTS,
        poll_interval_seconds=INTERACTIVE_LOG_POLL_INTERVAL_SECONDS,
        read_activity_events=read_interactive_activity_events,
        print_activity_events=print_interactive_activity_events,
        print_reply=print_assistant_reply,
    )


def interactive_daemon_status(project_root: Path | None) -> str:
    status = observe_daemon_status(project_root)
    if status is None:
        return "unknown"
    return "running" if status.running else (
        "one-shot" if status.phase == "stopped" else status.phase
    )
