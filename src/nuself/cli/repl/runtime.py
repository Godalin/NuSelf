"""Interactive REPL session loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.cli.repl.input import InteractiveInput
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult

SendMessage = Callable[[str, str, str | None], InteractiveChatResult]
HandleCommand = Callable[
    [str, Path | None, str, InteractiveSession],
    tuple[str, str],
]
SendTurn = Callable[
    [SendMessage, Path | None, str, str, InteractiveSession],
    int,
]


@dataclass(frozen=True)
class ReplCallbacks:
    handle_command: HandleCommand
    send_turn: SendTurn
    auto_save: Callable[[Path | None, InteractiveSession], None]
    run_curator: Callable[[Path | None], None]
    show_session_header: Callable[[Path | None, str], None]
    brand_banner: Callable[[], str]


def run_interactive_loop(
    send_message: SendMessage,
    project_root: Path | None,
    callbacks: ReplCallbacks,
    *,
    initial_thread_id: str = "default",
) -> int:
    interactive_input = InteractiveInput(project_root)
    current_thread_id = initial_thread_id
    session = InteractiveSession(connected_at=datetime.now(UTC))
    session.start_index_for(project_root, current_thread_id)
    print(callbacks.brand_banner())
    print(
        "νSelf interactive mode. Type :help for commands, "
        ":q to quit."
    )
    callbacks.show_session_header(project_root, current_thread_id)
    try:
        while True:
            try:
                line = interactive_input.read()
            except EOFError:
                print()
                callbacks.auto_save(project_root, session)
                return 0
            except KeyboardInterrupt:
                print()
                continue
            message = line.strip()
            if message == "":
                continue
            if message.startswith(":"):
                result, current_thread_id = callbacks.handle_command(
                    message,
                    project_root,
                    current_thread_id,
                    session,
                )
                session.start_index_for(
                    project_root, current_thread_id
                )
                if result == "exit":
                    return 0
                if result == "redraw_header":
                    callbacks.show_session_header(
                        project_root,
                        current_thread_id,
                    )
                continue
            try:
                result = callbacks.send_turn(
                    send_message,
                    project_root,
                    current_thread_id,
                    message,
                    session,
                )
            except KeyboardInterrupt:
                print("\nInterrupted.")
                continue
            callbacks.show_session_header(
                project_root,
                current_thread_id,
            )
            if result != 0:
                continue
    finally:
        callbacks.auto_save(project_root, session)
        callbacks.run_curator(project_root)
