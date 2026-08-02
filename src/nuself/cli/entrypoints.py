"""Typed launch policy for interactive CLI entrypoints."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nuself.conversation import ConversationState, ConversationStore
from nuself.cli.composition import cli_application
from nuself.cli.daemon_lifecycle import (
    start_daemon_observed,
)
from nuself.cli.daemon_status import format_status, observe_daemon_status
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.repl.types import InteractiveChatResult
from nuself.daemon import lifecycle
from nuself.notification.deep_link import DeepLink
from nuself.runtime.diagnostics import diagnostic_exception_message

InteractiveSender = Callable[
    [str, str, str | None],
    InteractiveChatResult,
]


class SendChat(Protocol):
    def __call__(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
    ) -> int: ...


class SendInteractiveChat(Protocol):
    def __call__(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult: ...


class RunInteractive(Protocol):
    def __call__(
        self,
        send_message: InteractiveSender,
        project_root: Path | None,
        *,
        initial_conversation_id: str = "default",
        daemon_activity: bool = False,
    ) -> int: ...


@dataclass(frozen=True)
class EntrypointCallbacks:
    """Capabilities supplied by the CLI composition root."""

    send_daemon_chat: SendChat
    send_daemon_chat_interactive: SendInteractiveChat
    send_one_shot_chat: SendChat
    send_one_shot_chat_interactive: SendInteractiveChat
    run_interactive: RunInteractive


@dataclass(frozen=True)
class _ConversationOpenTarget:
    conversation_id: str
    message: str | None


class EntrypointController:
    """Route entrypoint intent to daemon-backed or local chat capabilities."""

    def __init__(self, callbacks: EntrypointCallbacks) -> None:
        self._callbacks = callbacks

    def handle_default(self, args: argparse.Namespace) -> int:
        result = observe_daemon_status(args.project_root)
        if result is None:
            return CliExitCode.TEMPORARY_FAILURE
        if result.running:
            if args.message is not None:
                print(f"Using current daemon: {format_status(result)}")
        else:
            print("Starting NuSelf daemon...")
            try:
                transition = start_daemon_observed(
                    args.scope,
                    initial_status=result,
                )
            except lifecycle.DaemonStartError as exc:
                print(
                    "Failed to start daemon: "
                    f"{diagnostic_exception_message(exc)}",
                    file=sys.stderr,
                )
                return CliExitCode.FAILURE
            result = transition.status
            print(f"Daemon started: {format_status(result)}")
        if args.message is not None:
            return self._callbacks.send_daemon_chat(
                args.message,
                args.project_root,
            )
        return self._run_daemon_interactive(args.project_root)

    def handle_chat(self, args: argparse.Namespace) -> int:
        daemon_status = observe_daemon_status(args.project_root)
        if daemon_status is None:
            return CliExitCode.TEMPORARY_FAILURE
        if daemon_status.running:
            if args.message is not None:
                return self._callbacks.send_daemon_chat(
                    args.message,
                    args.project_root,
                )
            return self._run_daemon_interactive(args.project_root)
        if args.require_daemon or daemon_status.phase != "stopped":
            print(
                f"NuSelf daemon is not ready: {daemon_status.phase}.",
                file=sys.stderr,
            )
            return (
                CliExitCode.SETUP_REQUIRED
                if daemon_status.phase == "stopped"
                else CliExitCode.TEMPORARY_FAILURE
            )
        if args.message is not None:
            return self._callbacks.send_one_shot_chat(
                args.message,
                args.project_root,
            )
        return self._run_one_shot_interactive(args.project_root)

    def handle_attach(self, args: argparse.Namespace) -> int:
        daemon_status = observe_daemon_status(args.project_root)
        if daemon_status is None:
            return CliExitCode.TEMPORARY_FAILURE
        if not daemon_status.running:
            print(
                f"NuSelf daemon is not ready: {daemon_status.phase}.",
                file=sys.stderr,
            )
            return (
                CliExitCode.SETUP_REQUIRED
                if daemon_status.phase == "stopped"
                else CliExitCode.TEMPORARY_FAILURE
            )
        if args.message is not None:
            return self._callbacks.send_daemon_chat(
                args.message,
                args.project_root,
            )
        return self._run_daemon_interactive(args.project_root)

    def handle_open(self, args: argparse.Namespace) -> int:
        store = cli_application().conversations
        target = self._prepare_open_conversation(args, store)
        if target is None:
            return CliExitCode.FAILURE

        daemon_status = observe_daemon_status(args.project_root)
        if daemon_status is None:
            return CliExitCode.TEMPORARY_FAILURE
        if daemon_status.running:
            if target.message is not None:
                result = self._callbacks.send_daemon_chat(
                    target.message,
                    args.project_root,
                    target.conversation_id,
                )
                if result != CliExitCode.SUCCESS:
                    return result
            return self._run_daemon_interactive(
                args.project_root,
                initial_conversation_id=target.conversation_id,
            )
        if daemon_status.phase != "stopped":
            print(
                f"NuSelf daemon is not ready: {daemon_status.phase}.",
                file=sys.stderr,
            )
            return CliExitCode.TEMPORARY_FAILURE
        if target.message is not None:
            result = self._callbacks.send_one_shot_chat(
                target.message,
                args.project_root,
                target.conversation_id,
            )
            if result != CliExitCode.SUCCESS:
                return result
        return self._run_one_shot_interactive(
            args.project_root,
            initial_conversation_id=target.conversation_id,
        )

    def _prepare_open_conversation(
        self,
        args: argparse.Namespace,
        store: ConversationStore,
    ) -> _ConversationOpenTarget | None:
        conversation_id: str | None = args.conversation_id
        message: str | None = args.message
        if args.deep_link is not None:
            try:
                link = DeepLink.parse(args.deep_link)
            except ValueError as exc:
                print(
                    "Invalid deep link: "
                    f"{diagnostic_exception_message(exc)}",
                    file=sys.stderr,
                )
                return None
            if link.action == "new_conversation":
                conversation_id = link.title or "new-conversation"
                store.save(ConversationState.empty(conversation_id))
                print(f"Created conversation: {conversation_id}")
                if message is None and link.message is not None:
                    message = link.message
            else:
                conversation_id = link.conversation_id
                if message is None and link.message is not None:
                    message = link.message

        if conversation_id is None:
            print("Conversation ID or --deep-link is required.", file=sys.stderr)
            return None
        if conversation_id not in store.list():
            if args.create:
                store.save(ConversationState.empty(conversation_id))
                print(f"Created conversation: {conversation_id}")
            else:
                print(f"Conversation not found: {conversation_id}", file=sys.stderr)
                return None
        return _ConversationOpenTarget(conversation_id=conversation_id, message=message)

    def _run_daemon_interactive(
        self,
        project_root: Path | None,
        *,
        initial_conversation_id: str = "default",
    ) -> int:
        return self._callbacks.run_interactive(
            lambda message, conversation_id, turn_id: (
                self._callbacks.send_daemon_chat_interactive(
                    message,
                    project_root,
                    conversation_id,
                    turn_id=turn_id,
                )
            ),
            project_root,
            initial_conversation_id=initial_conversation_id,
            daemon_activity=True,
        )

    def _run_one_shot_interactive(
        self,
        project_root: Path | None,
        *,
        initial_conversation_id: str = "default",
    ) -> int:
        return self._callbacks.run_interactive(
            lambda message, conversation_id, turn_id: (
                self._callbacks.send_one_shot_chat_interactive(
                    message,
                    project_root,
                    conversation_id,
                    turn_id=turn_id,
                )
            ),
            project_root,
            initial_conversation_id=initial_conversation_id,
        )
