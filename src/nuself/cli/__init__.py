"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path

_original_warn = warnings.warn

TYPEWRITER_DELAY_SECONDS = 0.01
TYPEWRITER_REFRESH_PER_SECOND = 30


def _suppress_startup_warning(
    message: Warning | str,
    category: type[Warning] | None = None,
    stacklevel: int = 1,
    source: object | None = None,
) -> None:
    if "The default value of `allowed_objects` will change in a future version." in str(
        message
    ):
        return
    _original_warn(message, category=category, stacklevel=stacklevel, source=source)


warnings.warn = _suppress_startup_warning
try:
    from nuself import __version__
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
    from nuself.cli.entrypoints import (
        EntrypointCallbacks,
        EntrypointController,
    )
    from nuself.cli.repl.activity import (
        print_interactive_activity_events as _print_interactive_activity_events,
    )
    from nuself.cli.repl.activity import (
        read_interactive_activity_events as _interactive_activity_events,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_archive as handle_reflection_archive,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_dismiss as handle_reflection_dismiss,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_list as handle_reflection_list,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_show as handle_reflection_show,
    )
    from nuself.cli.handlers import dispatch_cli
    from nuself.cli.parser import (
        InteractiveHandlers,
    )
    from nuself.cli.parser import (
        build_parser as _build_parser,
    )
    from nuself.cli.repl.commands import (
        handle_interactive_reason_watch as _handle_interactive_reason_watch,
    )
    from nuself.cli.repl.dispatcher import (
        handle_interactive_command as _handle_interactive_command,
    )
    from nuself.cli.repl.input import (
        InteractiveCompleter as _InteractiveCompleter,
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
    from nuself.daemon import lifecycle
finally:
    warnings.warn = _original_warn

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch_cli(args, parser)


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
        InteractiveHandlers(
            default_entrypoint=entrypoints.handle_default,
            chat=entrypoints.handle_chat,
            attach=entrypoints.handle_attach,
            open_thread=entrypoints.handle_open,
            reason_watch=handle_reason_watch,
        )
    )


# ── Reason handlers ───────────────────────────────────────────────────


def handle_reason_watch(args: argparse.Namespace) -> int:
    _handle_interactive_reason_watch(
        args.project_root,
        interval=getattr(args, "interval", 5),
        thread_ref=getattr(args, "thread_id", None) or None,
    )
    return 0


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
            handle_command=_handle_interactive_command,
            send_turn=send_turn,
            auto_save=_auto_save_interactive_transcripts,
            run_curator=_run_memory_curator,
            show_session_header=header_presenter.show,
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
    status = lifecycle.status(project_root)
    return "running" if status.running else "one-shot"


if __name__ == "__main__":
    raise SystemExit(main())
