"""Interactive REPL session loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.cli.commands.output import print_ansi
from nuself.cli.repl.input import (
    init_interactive_input,
    read_interactive_input,
)
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult
from nuself.tui.render import render_session_header

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
    show_session_update: Callable[[Path | None, str], None]
    daemon_status: Callable[[Path | None], str]
    brand_banner: Callable[[], str]


def run_interactive_loop(
    send_message: SendMessage,
    project_root: Path | None,
    callbacks: ReplCallbacks,
    *,
    initial_thread_id: str = "default",
) -> int:
    init_interactive_input(project_root)
    current_thread_id = initial_thread_id
    session = InteractiveSession(connected_at=datetime.now(UTC))
    session.start_index_for(project_root, current_thread_id)
    print(callbacks.brand_banner())
    print(
        "νSelf interactive mode. Type :help for commands, "
        ":q to quit."
    )
    print_ansi(
        render_session_header(
            daemon_status=callbacks.daemon_status(project_root),
            thread_id=current_thread_id,
        )
    )
    try:
        while True:
            try:
                line = read_interactive_input()
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
                    print_ansi(
                        render_session_header(
                            daemon_status=callbacks.daemon_status(
                                project_root
                            ),
                            thread_id=current_thread_id,
                        )
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
            callbacks.show_session_update(
                project_root, current_thread_id
            )
            if result != 0:
                continue
    finally:
        callbacks.auto_save(project_root, session)
        callbacks.run_curator(project_root)
