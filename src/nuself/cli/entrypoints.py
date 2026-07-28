"""Typed launch policy for interactive CLI entrypoints."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli.daemon_lifecycle import (
    format_start_failure,
    start_daemon_observed,
)
from nuself.cli.daemon_status import format_status, observe_daemon_status
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
        thread_id: str = "default",
    ) -> int: ...


class SendInteractiveChat(Protocol):
    def __call__(
        self,
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult: ...


class RunInteractive(Protocol):
    def __call__(
        self,
        send_message: InteractiveSender,
        project_root: Path | None,
        *,
        initial_thread_id: str = "default",
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
class _OpenTarget:
    thread_id: str
    message: str | None


class EntrypointController:
    """Route entrypoint intent to daemon-backed or local chat capabilities."""

    def __init__(self, callbacks: EntrypointCallbacks) -> None:
        self._callbacks = callbacks

    def handle_default(self, args: argparse.Namespace) -> int:
        result = self._status_or_report(args.project_root)
        if result is None:
            return 1
        if result.running:
            if args.message is not None:
                print(f"Using current daemon: {format_status(result)}")
        else:
            print("Starting NuSelf daemon...")
            try:
                transition = start_daemon_observed(
                    args.project_root,
                    initial_status=result,
                )
            except lifecycle.DaemonStartError as exc:
                print(
                    f"Failed to start daemon: {format_start_failure(exc)}",
                    file=sys.stderr,
                )
                return 1
            result = transition.status
            print(f"Daemon started: {format_status(result)}")
        if args.message is not None:
            return self._callbacks.send_daemon_chat(
                args.message,
                args.project_root,
            )
        return self._run_daemon_interactive(args.project_root)

    def handle_chat(self, args: argparse.Namespace) -> int:
        daemon_status = self._status_or_report(args.project_root)
        if daemon_status is None:
            return 1
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
            return 1
        if args.message is not None:
            return self._callbacks.send_one_shot_chat(
                args.message,
                args.project_root,
            )
        return self._run_one_shot_interactive(args.project_root)

    def handle_attach(self, args: argparse.Namespace) -> int:
        daemon_status = self._status_or_report(args.project_root)
        if daemon_status is None:
            return 1
        if not daemon_status.running:
            print(
                f"NuSelf daemon is not ready: {daemon_status.phase}.",
                file=sys.stderr,
            )
            return 1
        if args.message is not None:
            return self._callbacks.send_daemon_chat(
                args.message,
                args.project_root,
            )
        return self._run_daemon_interactive(args.project_root)

    def handle_open(self, args: argparse.Namespace) -> int:
        store = ThreadStore(args.project_root)
        target = self._prepare_open_thread(args, store)
        if target is None:
            return 1

        daemon_status = self._status_or_report(args.project_root)
        if daemon_status is None:
            return 1
        if daemon_status.running:
            if target.message is not None:
                result = self._callbacks.send_daemon_chat(
                    target.message,
                    args.project_root,
                    target.thread_id,
                )
                if result != 0:
                    return result
            return self._run_daemon_interactive(
                args.project_root,
                initial_thread_id=target.thread_id,
            )
        if daemon_status.phase != "stopped":
            print(
                f"NuSelf daemon is not ready: {daemon_status.phase}.",
                file=sys.stderr,
            )
            return 1
        if target.message is not None:
            result = self._callbacks.send_one_shot_chat(
                target.message,
                args.project_root,
                target.thread_id,
            )
            if result != 0:
                return result
        return self._run_one_shot_interactive(
            args.project_root,
            initial_thread_id=target.thread_id,
        )

    @staticmethod
    def _status_or_report(
        project_root: Path | None,
    ) -> lifecycle.DaemonStatus | None:
        return observe_daemon_status(project_root)

    def _prepare_open_thread(
        self,
        args: argparse.Namespace,
        store: ThreadStore,
    ) -> _OpenTarget | None:
        thread_id: str | None = args.thread_id
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
            if link.action == "new_thread":
                thread_id = link.title or "new-thread"
                store.save(ThreadState.empty(thread_id))
                print(f"Created thread: {thread_id}")
                if message is None and link.message is not None:
                    message = link.message
            else:
                thread_id = link.thread_id
                if message is None and link.message is not None:
                    message = link.message

        if thread_id is None:
            print("Thread ID or --deep-link is required.", file=sys.stderr)
            return None
        if thread_id not in store.list():
            if args.create:
                store.save(ThreadState.empty(thread_id))
                print(f"Created thread: {thread_id}")
            else:
                print(f"Thread not found: {thread_id}", file=sys.stderr)
                return None
        return _OpenTarget(thread_id=thread_id, message=message)

    def _run_daemon_interactive(
        self,
        project_root: Path | None,
        *,
        initial_thread_id: str = "default",
    ) -> int:
        return self._callbacks.run_interactive(
            lambda message, thread_id, turn_id: (
                self._callbacks.send_daemon_chat_interactive(
                    message,
                    project_root,
                    thread_id,
                    turn_id=turn_id,
                )
            ),
            project_root,
            initial_thread_id=initial_thread_id,
            daemon_activity=True,
        )

    def _run_one_shot_interactive(
        self,
        project_root: Path | None,
        *,
        initial_thread_id: str = "default",
    ) -> int:
        return self._callbacks.run_interactive(
            lambda message, thread_id, turn_id: (
                self._callbacks.send_one_shot_chat_interactive(
                    message,
                    project_root,
                    thread_id,
                    turn_id=turn_id,
                )
            ),
            project_root,
            initial_thread_id=initial_thread_id,
        )
