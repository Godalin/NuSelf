"""Interactive input, history, completion, and help."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import prompt as _prompt
from prompt_toolkit.styles import Style

from nuself.agent.chat import ThreadStore
from nuself.cli.repl.registry import (
    command_tokens,
    render_help_lines,
    tokens_for,
)
from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.runtime.observability import run_observed_best_effort


class DedupFileHistory(FileHistory):
    """FileHistory that skips consecutive duplicate entries."""

    def __init__(
        self,
        filename: str,
        *,
        project_root: Path | None,
    ) -> None:
        super().__init__(filename)
        self._project_root = project_root

    def append_string(self, string: str) -> None:
        run_observed_best_effort(
            lambda: self._append_string(string),
            component="chat",
            event="interactive_history_write_failed",
            message="Failed to persist interactive input history",
            project_root=self._project_root,
        )

    def _append_string(self, string: str) -> None:
        loaded = self.get_strings()
        if loaded and loaded[-1] == string:
            return
        FileHistory.append_string(self, string)


_PROMPT_STYLE = Style.from_dict({
    "ansicyan": "ansicyan bold",
})

_PROMPT_TEXT = FormattedText([("class:ansicyan bold", "\nNuSelf> ")])

class InteractiveCompleter(Completer):
    def __init__(self, project_root: Path | None) -> None:
        super().__init__()
        self._project_root = project_root

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        text = document.text_before_cursor
        stripped = text.lstrip()
        word = text.split()[-1] if text.split() else ""

        if any(
            stripped.startswith(f"{token} ")
            for token in tokens_for("thread")
        ) and word and not word.startswith(":"):
            yield from self._thread_completions(word)
            return
        if stripped.startswith(":unarchive ") and word and not word.startswith(":"):
            yield from self._archived_thread_completions(word)
            return
        if text.rstrip().endswith(tokens_for("reason")):
            for cmd, desc, _ in self._REASON_SUBCOMMANDS:
                yield Completion(f"{cmd} ", start_position=0, display=cmd, display_meta=desc)
            return
        if any(
            stripped.startswith(f"{token} ")
            for token in tokens_for("reason")
        ) and word and not word.startswith(":"):
            yield from self._reason_subcommand_completions(stripped, word)
            return
        if word.startswith(":"):
            for cmd in command_tokens():
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))

    _REASON_SUBCOMMANDS: list[tuple[str, str, bool]] = [
        ("list", "List active and paused reasoning threads", False),
        ("show", "Show details for a reasoning thread", True),
        ("start", "Create a new reasoning thread from a topic", False),
        ("advance", "Advance a thread with the next reasoning step", True),
        ("pause", "Pause a reasoning thread", True),
        ("resume", "Resume a paused reasoning thread", True),
        ("resolve", "Mark a reasoning thread as resolved", True),
        ("archive", "Archive a resolved or inactive thread", True),
        ("delete", "Permanently delete a reasoning thread", True),
        ("watch", "Watch for new reasoning steps in real-time", False),
    ]

    def _reason_subcommand_completions(self, stripped: str, word: str) -> Iterable[Completion]:
        prefix = stripped.removeprefix(
            f"{tokens_for('reason')[0]} "
        )
        subcmd = prefix.split()[0] if prefix.strip() else ""
        # After a subcommand that takes a thread id, offer thread completions
        needs_id = any(cmd == subcmd for cmd, _, needs in self._REASON_SUBCOMMANDS if needs)
        if subcmd and needs_id and prefix.strip() != subcmd:
            thread_words = prefix.removeprefix(subcmd).strip()
            for tid in self._all_thread_ids_with_status():
                if thread_words == "" or tid.startswith(thread_words):
                    yield Completion(tid, start_position=-len(thread_words) if thread_words else 0)
            return
        # Offer subcommand completions with descriptions
        for cmd, desc, _ in self._REASON_SUBCOMMANDS:
            if cmd.startswith(word):
                yield Completion(f"{cmd} ", start_position=-len(word), display=cmd, display_meta=desc)

    def _all_thread_ids_with_status(self) -> list[str]:
        def load() -> list[str]:
            from nuself.reason.repository import ReasonRepository

            repo = ReasonRepository(self._project_root)
            return [f"{t.id} ({t.status}, {t.topic[:40]})" for t in repo.list_threads(status="all")]

        return (
            run_observed_best_effort(
                load,
                component="reasoning",
                event="completion_load_failed",
                message="Failed to load reason thread completions",
                project_root=self._project_root,
                metadata={"completion": "reason_threads"},
            )
            or []
        )

    def _thread_completions(self, word: str) -> Iterable[Completion]:
        threads = (
            run_observed_best_effort(
                lambda: ThreadStore(self._project_root).list(),
                component="chat",
                event="completion_load_failed",
                message="Failed to load thread completions",
                project_root=self._project_root,
                metadata={"completion": "threads"},
            )
            or []
        )
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))

    def _archived_thread_completions(self, word: str) -> Iterable[Completion]:
        threads = (
            run_observed_best_effort(
                lambda: ThreadStore(self._project_root).list_archived(),
                component="chat",
                event="completion_load_failed",
                message="Failed to load archived thread completions",
                project_root=self._project_root,
                metadata={"completion": "archived_threads"},
            )
            or []
        )
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))


class InteractiveInput:
    """History and completion state owned by one interactive loop."""

    def __init__(self, project_root: Path | None) -> None:
        paths = runtime_paths(project_root)
        ensure_runtime_dirs(paths)
        self._project_root = paths.project_root
        history_path = paths.runtime_dir / "interactive_history"
        self.history: FileHistory = DedupFileHistory(
            str(history_path),
            project_root=project_root,
        )
        self.completer = InteractiveCompleter(project_root)

    def read(self) -> str:
        """Read styled input, falling back to built-in input."""

        styled = run_observed_best_effort(
            self._read_styled,
            component="chat",
            event="interactive_prompt_failed",
            message="Styled interactive input failed; using built-in input",
            project_root=self._project_root,
            metadata={"fallback": "builtin_input"},
            errors=(AttributeError, OSError),
        )
        if styled is not None:
            return styled
        line = input("NuSelf> ")
        self.append_history(line)
        return line

    def _read_styled(self) -> str | None:
        if not sys.stdin.isatty():
            return None
        return _prompt(
            _PROMPT_TEXT,
            style=_PROMPT_STYLE,
            history=self.history,
            completer=self.completer,
        )

    def append_history(self, line: str) -> None:
        if line:
            self.history.append_string(line)


def interactive_command_hints(partial: str) -> list[str]:
    return [
        cmd
        for cmd in command_tokens()
        if cmd.startswith(partial) and cmd != partial
    ]


def interactive_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown interactive command: {command}")
        hints = interactive_command_hints(command)
        if hints:
            lines.append(f"Did you mean: {', '.join(hints)}?")
    lines.extend(["Interactive commands:", *render_help_lines()])
    return "\n".join(lines)
