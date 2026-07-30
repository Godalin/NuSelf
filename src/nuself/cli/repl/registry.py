"""Authoritative top-level REPL command names, aliases, and help."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplCommand:
    name: str
    aliases: tuple[str, ...] = ()
    help_lines: tuple[str, ...] = ()

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(f":{item}" for item in (self.name, *self.aliases))


@dataclass(frozen=True)
class ResolvedReplCommand:
    name: str
    body: str


REPL_COMMANDS: tuple[ReplCommand, ...] = (
    ReplCommand(
        "q",
        ("quit", "exit"),
        ("  :q         exit", "  :quit      exit", "  :exit      exit"),
    ),
    ReplCommand("history", help_lines=("  :history   show recent thread messages",)),
    ReplCommand("whoami", help_lines=("  :whoami    show core profile",)),
    ReplCommand(
        "inbox",
        ("i",),
        (
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
        ),
    ),
    ReplCommand("help", help_lines=("  :help      show this help",)),
    ReplCommand(
        "retry",
        help_lines=("  :retry     safely retry the last retryable chat turn",),
    ),
    ReplCommand(
        "dev",
        help_lines=(
            "  :dev status                   show daemon and thread status",
            "  :dev logs                     show recent activity logs",
        ),
    ),
    ReplCommand(
        "export",
        ("e",),
        (
            "  :export [all] [noclip]    save and copy this connection's transcript",
            "  :e [all] [noclip]         shorthand for :export",
        ),
    ),
    ReplCommand(
        "mem",
        ("m",),
        (
            "  :mem, :m                  preview memory entries",
            "  :mem search <query>       search memory entries",
            "  :mem show <entry-id>      show one memory entry",
            "  :mem review               list pending memory review items",
            "  :mem review <id>          show one memory review item",
            "  :mem profile <query>      search profile items",
            "  :mem sources              list imported sources",
            "  :mem source <source-id>   show one source",
        ),
    ),
    ReplCommand(
        "thread",
        ("t",),
        (
            "  :thread, :t               list active threads",
            "  :thread <id>, :t <id>     switch to or create a thread",
        ),
    ),
    ReplCommand("reason", help_lines=("  :reason                   long-run reasoning commands",)),
    ReplCommand(
        "trace",
        help_lines=(
            "  :trace                    list thought trace records",
            "  :trace show <id|index>    show one thought trace",
            "  :trace search <query>     search thought trace records",
        ),
    ),
    ReplCommand("persona", ("p",), ("  :persona, :p             list/manage custom personas",)),
    ReplCommand("restart", ("r",), ("  :restart, :r              restart daemon and reconnect",)),
    ReplCommand("rename", help_lines=("  :rename <new-id>          rename the current thread",)),
    ReplCommand("branch", help_lines=("  :branch <new-id> [index]  branch current thread at index",)),
    ReplCommand("archive", help_lines=("  :archive                  archive the current thread",)),
    ReplCommand("unarchive", help_lines=("  :unarchive <id>           restore an archived thread",)),
    ReplCommand("archived", help_lines=("  :archived                 list archived threads",)),
    ReplCommand("delete", help_lines=("  :delete                   delete the current thread",)),
)


def _index_commands(
    commands: tuple[ReplCommand, ...],
) -> tuple[dict[str, ReplCommand], dict[str, ReplCommand]]:
    by_name: dict[str, ReplCommand] = {}
    by_token: dict[str, ReplCommand] = {}
    for command in commands:
        if command.name in by_name:
            raise ValueError(
                f"duplicate REPL command name: {command.name!r}"
            )
        by_name[command.name] = command
        for token in command.tokens:
            if token in by_token:
                raise ValueError(
                    f"duplicate REPL command token: {token!r}"
                )
            by_token[token] = command
    return by_name, by_token


_BY_NAME, _BY_TOKEN = _index_commands(REPL_COMMANDS)


def command_names() -> tuple[str, ...]:
    return tuple(_BY_NAME)


def command_tokens() -> tuple[str, ...]:
    return tuple(
        token
        for command in REPL_COMMANDS
        for token in command.tokens
    )


def tokens_for(name: str) -> tuple[str, ...]:
    return _BY_NAME[name].tokens


def command_body(text: str, name: str) -> str | None:
    """Return arguments when text resolves to name, otherwise None."""
    for token in tokens_for(name):
        if text == token:
            return ""
        prefix = f"{token} "
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return None


def command_matches(text: str, name: str) -> bool:
    return command_body(text, name) == ""


def resolve_command(text: str) -> ResolvedReplCommand | None:
    """Resolve a complete input to one canonical command and argument body."""
    token, separator, remainder = text.partition(" ")
    command = _BY_TOKEN.get(token)
    if command is None:
        return None
    return ResolvedReplCommand(
        name=command.name,
        body=remainder.strip() if separator else "",
    )


def render_help_lines() -> list[str]:
    return [
        line
        for command in REPL_COMMANDS
        for line in command.help_lines
    ]
