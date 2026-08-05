"""Interactive REPL session loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.cli.repl.input import InteractiveInput
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult
from nuself.agent.chat.audit import CHAT_AUDIT
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.runtime.feature.effect import ToolEffectResolution

type SendMessage = Callable[
    [str, str, str | None, ToolEffectResolution | None],
    InteractiveChatResult,
]
type HandleCommand = Callable[
    [str, Path | None, str, InteractiveSession],
    tuple[str, str],
]
type SendTurn = Callable[
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
        CHAT_AUDIT.failure(
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
    initial_conversation_id: str = "default",
) -> int:
    interactive_input = InteractiveInput(project_root)
    current_conversation_id = initial_conversation_id
    session = InteractiveSession(connected_at=datetime.now(UTC))
    session.start_index_for(project_root, current_conversation_id)
    print(callbacks.brand_banner())
    print(
        "νSelf interactive mode. Type :help for commands, "
        ":q to quit."
    )
    callbacks.show_session_header(project_root, current_conversation_id)
    callbacks.show_startup_notices(project_root)

    def run_loop() -> int:
        nonlocal current_conversation_id
        while True:
            try:
                line = interactive_input.read()
            except EOFError:
                print()
                return CliExitCode.SUCCESS
            except KeyboardInterrupt:
                print()
                continue
            message = line.strip()
            if message == "":
                continue
            if message.startswith(":"):
                previous_conversation_id = current_conversation_id
                result, current_conversation_id = callbacks.handle_command(
                    message,
                    project_root,
                    current_conversation_id,
                    session,
                )
                session.start_index_for(
                    project_root, current_conversation_id
                )
                if current_conversation_id != previous_conversation_id:
                    session.clear_retry()
                if result == "exit":
                    return CliExitCode.SUCCESS
                if result == "retry":
                    offer = session.retry_offer
                    if offer is None:
                        raise RuntimeError(
                            "interactive retry was requested without an offer"
                        )
                    try:
                        callbacks.send_turn(
                            send_message,
                            project_root,
                            offer.conversation_id,
                            offer.message,
                            session,
                        )
                    except KeyboardInterrupt:
                        session.retry_requested = False
                        print("\nInterrupted.")
                    callbacks.show_session_header(
                        project_root,
                        current_conversation_id,
                    )
                    continue
                if result == "redraw_header":
                    callbacks.show_session_header(
                        project_root,
                        current_conversation_id,
                    )
                continue
            try:
                result = callbacks.send_turn(
                    send_message,
                    project_root,
                    current_conversation_id,
                    message,
                    session,
                )
            except KeyboardInterrupt:
                print("\nInterrupted.")
                continue
            callbacks.show_session_header(
                project_root,
                current_conversation_id,
            )
            if result != CliExitCode.SUCCESS:
                continue

    primary_error: BaseException | None = None
    result: int = CliExitCode.SUCCESS
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
