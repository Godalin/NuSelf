"""Interactive REPL session loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.cli.repl.input import InteractiveInput
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult
from nuself.agent.chat.audit import report_chat_failure
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps

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
    show_startup_notices: Callable[[Path | None], None]
    brand_banner: Callable[[], str]


class InteractiveLifecycleError(RuntimeError):
    """Raised when interactive exit cleanup retains one or more failures."""

    def __init__(
        self,
        failures: tuple[CleanupFailure, ...],
        *,
        primary_error: BaseException | None = None,
    ) -> None:
        super().__init__(
            f"interactive cleanup failed in {len(failures)} step(s)"
        )
        self.failures = failures
        self.primary_error = primary_error


def _run_interactive_cleanup(
    callbacks: ReplCallbacks,
    project_root: Path | None,
    session: InteractiveSession,
) -> tuple[CleanupFailure, ...]:
    steps: tuple[tuple[str, Callable[[], None]], ...] = (
        (
            "transcript.auto_save",
            lambda: callbacks.auto_save(project_root, session),
        ),
        (
            "memory.curator.run",
            lambda: callbacks.run_curator(project_root),
        ),
    )
    return run_cleanup_steps(steps)


def _finish_interactive_lifecycle(
    *,
    project_root: Path | None,
    primary_error: BaseException | None,
    cleanup_failures: tuple[CleanupFailure, ...],
) -> None:
    if cleanup_failures:
        lifecycle_error = InteractiveLifecycleError(
            cleanup_failures,
            primary_error=primary_error,
        )
        report_chat_failure(
            lifecycle_error,
            event="interactive_cleanup_failed",
            project_root=project_root,
            metadata={
                "steps": [
                    failure.step for failure in cleanup_failures
                ],
                "primary_failed": primary_error is not None,
            },
        )
        if primary_error is not None:
            raise lifecycle_error from primary_error
        raise lifecycle_error
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)


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
    callbacks.show_startup_notices(project_root)

    def run_loop() -> int:
        nonlocal current_thread_id
        while True:
            try:
                line = interactive_input.read()
            except EOFError:
                print()
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

    primary_error: BaseException | None = None
    result = 0
    try:
        result = run_loop()
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = _run_interactive_cleanup(
        callbacks,
        project_root,
        session,
    )
    _finish_interactive_lifecycle(
        project_root=project_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return result
