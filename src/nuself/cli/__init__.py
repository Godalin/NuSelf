"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
import sys
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

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

from nuself.cli.exit_codes import CliExitCode
from nuself.cli.entrypoints import (
    EntrypointCallbacks,
    EntrypointController,
)
from nuself.cli.handlers import dispatch_cli
from nuself.application.runtime import use_application_runtime
from nuself.cli.parser import (
    EntrypointHandlers,
)
from nuself.cli.parser import (
    build_parser as _build_parser,
)
from nuself.cli.presentation import print_assistant_reply
from nuself.cli.repl.composition import run_repl
from nuself.cli.repl.types import InteractiveChatResult
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.scope import resolve_scope
from nuself.application.runtime import open_application_runtime
from nuself.storage_audit import report_cli_cleanup_failure

__all__ = [
    "build_parser",
    "main",
]

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
    application_runtime = open_application_runtime(scope)
    try:
        with use_application_runtime(application_runtime):
            result = dispatch_cli(args, parser)
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = run_cleanup_steps(
        (
            (
                "application_runtime.close",
                application_runtime.close,
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
            open_conversation=entrypoints.handle_open,
        )
    )


def _send_chat(
    message: str, project_root: Path | None, conversation_id: str = "default"
) -> int:
    return _send_daemon_chat(
        message,
        project_root,
        conversation_id,
        print_reply=print_assistant_reply,
    )


def _interactive_loop(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    *,
    initial_conversation_id: str = "default",
    daemon_activity: bool = False,
) -> int:
    return run_repl(
        send_message,
        project_root,
        run_memory_curator=_run_memory_curator,
        initial_conversation_id=initial_conversation_id,
        daemon_activity=daemon_activity,
    )


def _send_one_shot_chat(
    message: str, project_root: Path | None, conversation_id: str = "default"
) -> int:
    return _run_one_shot_chat(
        message,
        project_root,
        conversation_id,
        print_reply=print_assistant_reply,
    )


if __name__ == "__main__":
    raise SystemExit(main())
