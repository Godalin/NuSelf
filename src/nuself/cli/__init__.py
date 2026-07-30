"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

TYPEWRITER_DELAY_SECONDS = 0.01
TYPEWRITER_REFRESH_PER_SECOND = 30

from nuself import __version__

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=(
            r"^The default value of `allowed_objects` will change in a future version\. "
            r"Pass an explicit value \(e\.g\., allowed_objects='messages' or "
            r"allowed_objects='core'\) to suppress this warning\.$"
        ),
        category=LangChainPendingDeprecationWarning,
    )
    from nuself.cli.chat import (
        run_memory_curator as _run_memory_curator,
    )
    from nuself.cli.chat import (
        send_daemon_chat as _send_daemon_chat,
    )
    from nuself.cli.chat import (
        send_daemon_chat_interactive as _send_chat_interactive,
    )
    from nuself.cli.chat import (
        send_one_shot_chat as _run_one_shot_chat,
    )
    from nuself.cli.chat import (
        send_one_shot_chat_interactive as _send_one_shot_chat_interactive,
    )

from nuself.cli.commands.reflections import (
    handle_reflection_archive as handle_reflection_archive,
)
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.commands.reflections import (
    handle_reflection_dismiss as handle_reflection_dismiss,
)
from nuself.cli.commands.reflections import (
    handle_reflection_list as handle_reflection_list,
)
from nuself.cli.commands.reflections import (
    handle_reflection_show as handle_reflection_show,
)
from nuself.cli.daemon_status import observe_daemon_status
from nuself.cli.entrypoints import (
    EntrypointCallbacks,
    EntrypointController,
)
from nuself.cli.handlers import dispatch_cli
from nuself.cli.parser import (
    EntrypointHandlers,
)
from nuself.cli.parser import (
    build_parser as _build_parser,
)
from nuself.cli.repl.activity import (
    print_interactive_activity_events as _print_interactive_activity_events,
)
from nuself.cli.repl.activity import (
    read_interactive_activity_events as _interactive_activity_events,
)
from nuself.cli.repl.dispatcher import (
    ReplCommandDispatcher,
)
from nuself.cli.repl.input import (
    InteractiveCompleter as _InteractiveCompleter,
)
from nuself.cli.repl.notices import (
    print_interactive_notices,
    startup_interactive_notices,
)
from nuself.cli.repl.presentation import SessionHeaderPresenter
from nuself.cli.repl.runtime import (
    ReplCallbacks,
    run_interactive_loop,
)
from nuself.cli.repl.session import (
    InteractiveSession as InteractiveSession,
)
from nuself.cli.repl.transcript import (
    auto_save_interactive_transcripts as _auto_save_interactive_transcripts,
)
from nuself.cli.repl.transcript import (
    render_chat_transcript as _render_chat_transcript,
)
from nuself.cli.repl.turns import (
    send_interactive_chat_turn as _run_interactive_chat_turn,
)
from nuself.cli.repl.types import InteractiveChatResult
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.scope import resolve_scope
from nuself.storage import reset_default_backend
from nuself.storage_audit import report_cli_cleanup_failure

__all__ = [
    "_InteractiveCompleter",
    "_render_chat_transcript",
    "build_parser",
    "main",
]

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_MEMORY_PREVIEW_LIMIT = 8
INTERACTIVE_CHAT_ATTEMPTS = 2
INTERACTIVE_LOG_POLL_INTERVAL_SECONDS = 0.1


class CliLifecycleError(RuntimeError):
    """Raised when outer CLI storage teardown fails."""

    def __init__(
        self,
        failures: tuple[CleanupFailure, ...],
        *,
        primary_error: BaseException | None = None,
    ) -> None:
        super().__init__(
            f"CLI cleanup failed in {len(failures)} step(s)"
        )
        self.failures = failures
        self.primary_error = primary_error


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        scope = resolve_scope(
            local=args.local,
            workspace=args.workspace,
        )
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return CliExitCode.INTERRUPTED
    args.scope = scope
    args.project_root = scope.root
    project_root = scope.root
    primary_error: BaseException | None = None
    result: int = CliExitCode.SUCCESS
    try:
        result = dispatch_cli(args, parser)
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = run_cleanup_steps(
        (
            (
                "storage.default_backend.reset",
                lambda: reset_default_backend(project_root),
            ),
        )
    )
    if cleanup_failures:
        lifecycle_error = CliLifecycleError(
            cleanup_failures,
            primary_error=primary_error,
        )
        report_cli_cleanup_failure(
            lifecycle_error,
            project_root=project_root,
            failures=cleanup_failures,
            primary_failed=primary_error is not None,
        )
        if primary_error is not None:
            raise lifecycle_error from primary_error
        raise lifecycle_error
    if primary_error is not None:
        if isinstance(primary_error, KeyboardInterrupt):
            print("Interrupted.", file=sys.stderr)
            return CliExitCode.INTERRUPTED
        raise primary_error.with_traceback(primary_error.__traceback__)
    return result


def build_parser() -> argparse.ArgumentParser:
    entrypoints = EntrypointController(
        EntrypointCallbacks(
            send_daemon_chat=_send_chat,
            send_daemon_chat_interactive=_send_chat_interactive,
            send_one_shot_chat=_send_one_shot_chat,
            send_one_shot_chat_interactive=_send_one_shot_chat_interactive,
            run_interactive=_interactive_loop,
        )
    )
    return _build_parser(
        EntrypointHandlers(
            default_entrypoint=entrypoints.handle_default,
            chat=entrypoints.handle_chat,
            attach=entrypoints.handle_attach,
            open_thread=entrypoints.handle_open,
        )
    )


def _send_chat(
    message: str, project_root: Path | None, thread_id: str = "default"
) -> int:
    return _send_daemon_chat(
        message,
        project_root,
        thread_id,
        print_reply=_print_assistant_reply,
    )


def _interactive_loop(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    *,
    initial_thread_id: str = "default",
    daemon_activity: bool = False,
) -> int:
    header_presenter = SessionHeaderPresenter(
        _interactive_daemon_status
    )
    command_dispatcher = ReplCommandDispatcher()

    def send_turn(
        turn_sender: Callable[
            [str, str, str | None],
            InteractiveChatResult,
        ],
        turn_project_root: Path | None,
        thread_id: str,
        message: str,
        session: InteractiveSession,
    ) -> int:
        return _send_interactive_chat_turn(
            turn_sender,
            turn_project_root,
            thread_id,
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
            auto_save=_auto_save_interactive_transcripts,
            run_curator=_run_memory_curator,
            show_session_header=header_presenter.show,
            show_startup_notices=lambda root: print_interactive_notices(
                startup_interactive_notices(root)
            ),
            brand_banner=_brand_banner,
        ),
        initial_thread_id=initial_thread_id,
    )


def _send_interactive_chat_turn(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    thread_id: str,
    message: str,
    session: InteractiveSession,
    *,
    daemon_activity: bool = False,
) -> int:
    return _run_interactive_chat_turn(
        send_message,
        project_root,
        thread_id,
        message,
        session,
        daemon_activity=daemon_activity,
        max_attempts=INTERACTIVE_CHAT_ATTEMPTS,
        poll_interval_seconds=INTERACTIVE_LOG_POLL_INTERVAL_SECONDS,
        read_activity_events=_interactive_activity_events,
        print_activity_events=_print_interactive_activity_events,
        print_reply=_print_assistant_reply,
    )


def _send_one_shot_chat(
    message: str, project_root: Path | None, thread_id: str = "default"
) -> int:
    return _run_one_shot_chat(
        message,
        project_root,
        thread_id,
        print_reply=_print_assistant_reply,
    )


def _brand_banner() -> str:
    return "\n".join(
        [
            "        ┌────┐       ┌─┐  ┌────┐",
            "        │ ┌──┘       │ │  │ ┌──┘",
            "╭─╮ ╭─╮ │ └──┐ ┌───┐ │ │  │ └─┐ ",
            "│ │ │ │ └──┐ │ │┌─ │ │ │  │ ┌─┘ ",
            "╰─┴─╯ │ ┌──┘ │ │└──╯ │ └┐ │ │   ",
            "  ╰───╯ └────┘ ╰───╯ └──┘ └─┘   ",
        ]
    )


def _print_assistant_reply(text: str) -> None:
    if not sys.stdout.isatty():
        print(text)
        return
    _render_assistant_reply_rich(text)


def _render_assistant_reply_rich(text: str) -> None:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown

    console = Console()
    if text == "":
        console.print("")
        return

    visible_text = ""
    with Live(
        Markdown(""),
        console=console,
        refresh_per_second=TYPEWRITER_REFRESH_PER_SECOND,
        transient=False,
    ) as live:
        for character in text:
            visible_text += character
            live.update(Markdown(visible_text))
            time.sleep(TYPEWRITER_DELAY_SECONDS)


def _interactive_daemon_status(project_root: Path | None) -> str:
    status = observe_daemon_status(project_root)
    if status is None:
        return "unknown"
    return "running" if status.running else (
        "one-shot" if status.phase == "stopped" else status.phase
    )


if __name__ == "__main__":
    raise SystemExit(main())
