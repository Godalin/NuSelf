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
from nuself.config import ensure_runtime_dirs, runtime_paths


class DedupFileHistory(FileHistory):
    """FileHistory that skips consecutive duplicate entries."""

    def append_string(self, string: str) -> None:
        loaded = self.get_strings()
        if loaded and loaded[-1] == string:
            return
        super().append_string(string)


_PROMPT_STYLE = Style.from_dict({
    "ansicyan": "ansicyan bold",
})

_PROMPT_TEXT = FormattedText([("class:ansicyan bold", "\nNuSelf> ")])

_history: FileHistory | None = None
_interactive_completer: InteractiveCompleter | None = None


def init_interactive_input(project_root: Path | None) -> None:
    global _history, _interactive_completer
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    history_path = paths.runtime_dir / "interactive_history"
    _history = DedupFileHistory(str(history_path))
    _interactive_completer = InteractiveCompleter(project_root)


def read_interactive_input() -> str:
    """Read a line of input with prompt_toolkit (styled), falling back to input()."""
    try:
        if sys.stdin.isatty():
            assert _history is not None
            return _prompt(
                _PROMPT_TEXT,
                style=_PROMPT_STYLE,
                history=_history,
                completer=_interactive_completer,
            )
    except (AttributeError, OSError):
        pass
    line = input("NuSelf> ")
    append_history(line)
    return line


def append_history(line: str) -> None:
    if _history is not None and line:
        _history.append_string(line)


_INTERACTIVE_COMMANDS = [
    ":q",
    ":quit",
    ":exit",
    ":history",
    ":whoami",
    ":help",
    ":export",
    ":e",
    ":mem",
    ":m",
    ":inbox",
    ":i",
    ":thread",
    ":t",
    ":reason",
    ":trace",
    ":persona", ":p",
    ":restart",
    ":r",
    ":dev",
    ":rename",
    ":branch",
    ":archive",
    ":unarchive",
    ":archived",
    ":delete",
]


class InteractiveCompleter(Completer):
    def __init__(self, project_root: Path | None) -> None:
        super().__init__()
        self._project_root = project_root

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        text = document.text_before_cursor
        stripped = text.lstrip()
        word = text.split()[-1] if text.split() else ""

        if (stripped.startswith(":thread ") or stripped.startswith(":t ")) and word and not word.startswith(":"):
            yield from self._thread_completions(word)
            return
        if stripped.startswith(":unarchive ") and word and not word.startswith(":"):
            yield from self._archived_thread_completions(word)
            return
        if text.rstrip().endswith(":reason") or text.rstrip().endswith(":re"):
            # Cursor at :reason or :re — offer all subcommands
            for cmd, desc, _ in self._REASON_SUBCOMMANDS:
                yield Completion(f"{cmd} ", start_position=0, display=cmd, display_meta=desc)
            return
        if (stripped.startswith(":reason ") or stripped.startswith(":re ")) and word and not word.startswith(":"):
            yield from self._reason_subcommand_completions(stripped, word)
            return
        if word.startswith(":"):
            for cmd in _INTERACTIVE_COMMANDS:
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
        prefix = stripped.removeprefix(":reason ").removeprefix(":re ")
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
        try:
            from nuself.reason.repository import ReasonRepository
            repo = ReasonRepository(self._project_root)
            return [f"{t.id} ({t.status}, {t.topic[:40]})" for t in repo.list_threads(status="all")]
        except Exception:
            return []

    def _thread_completions(self, word: str) -> Iterable[Completion]:
        try:
            threads = ThreadStore(self._project_root).list()
        except Exception:
            return ()
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))

    def _archived_thread_completions(self, word: str) -> Iterable[Completion]:
        try:
            threads = ThreadStore(self._project_root).list_archived()
        except Exception:
            return ()
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))


def interactive_command_hints(partial: str) -> list[str]:
    return [cmd for cmd in _INTERACTIVE_COMMANDS if cmd.startswith(partial) and cmd != partial]


def interactive_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown interactive command: {command}")
        hints = interactive_command_hints(command)
        if hints:
            lines.append(f"Did you mean: {', '.join(hints)}?")
    lines.extend(
        [
            "Interactive commands:",
            "  :q         exit",
            "  :quit      exit",
            "  :exit      exit",
            "  :history   show recent thread messages",
            "  :whoami    show core profile",
            "  :inbox, :i                    list pending reflections and notifications",
            "  :inbox reflection             list pending reflection ideas",
            "  :inbox reflection list        list reflection ideas",
            "  :inbox reflection show <id>   show one reflection idea",
            "  :inbox reflection dismiss <id> dismiss a reflection idea",
            "  :inbox reflection archive <id> archive a reflection idea",
            "  :inbox reflection promote <id> promote a reflection into reason",
            "  :inbox notify                 list pending notifications",
            "  :inbox notify list            list all notifications",
            "  :inbox notify show <id>       show one notification",
            "  :inbox notify send <id>       send a notification",
            "  :inbox notify dismiss <id>    dismiss a notification",
            "  :inbox notify watch           watch outbox for new entries",
            "  :help      show this help",
            "  :dev status                   show daemon and thread status",
            "  :dev logs                     show recent activity logs",
            "  :export [all] [noclip]    save and copy this connection's transcript",
            "  :e [all] [noclip]         shorthand for :export",
            "  :mem, :m                  preview memory entries",
            "  :mem search <query>       search memory entries",
            "  :mem show <entry-id>      show one memory entry",
            "  :mem review               list pending memory review items",
            "  :mem review <id>          show one memory review item",
            "  :mem profile <query>      search profile items",
            "  :mem sources              list imported sources",
            "  :mem source <source-id>   show one source",
            "  :thread, :t               list active threads",
            "  :thread <id>, :t <id>     switch to or create a thread",
            "  :reason                   long-run reasoning commands",
            "  :persona, :p             list/manage custom personas",
            "  :trace                    list thought trace records",
            "  :trace show <id|index>    show one thought trace",
            "  :trace search <query>     search thought trace records",
            "  :restart, :r              restart daemon and reconnect",
            "  :rename <new-id>          rename the current thread",
            "  :branch <new-id> [index]  branch current thread at index",
            "  :archive                  archive the current thread",
            "  :unarchive <id>           restore an archived thread",
            "  :archived                 list archived threads",
            "  :delete                   delete the current thread",
        ]
    )
    return "\n".join(lines)
