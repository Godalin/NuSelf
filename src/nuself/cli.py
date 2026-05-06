"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys

try:
    import readline
except ImportError:  # pragma: no cover - platform fallback
    readline = None  # type: ignore[assignment]

from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.agent.chat import ChatAgent
from nuself.daemon import client, lifecycle
from nuself.domain.memory import MemoryEntry, MemoryEntryType
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        help_parser = getattr(args, "help_parser", parser)
        help_parser.print_help()
        return 0
    return handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nuself")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--message", "-m", default=None)
    _add_handler(parser, handle_default_entrypoint)
    subparsers = parser.add_subparsers(dest="command")

    daemon_parser = subparsers.add_parser("daemon")
    daemon_parser.set_defaults(handler=None, help_parser=daemon_parser)
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command")
    _add_handler(daemon_subparsers.add_parser("start"), handle_daemon_start)
    _add_handler(daemon_subparsers.add_parser("stop"), handle_daemon_stop)
    _add_handler(daemon_subparsers.add_parser("status"), handle_daemon_status)
    _add_handler(daemon_subparsers.add_parser("list"), handle_daemon_list)
    _add_handler(daemon_subparsers.add_parser("logs"), handle_daemon_logs)
    daemon_attach_parser = daemon_subparsers.add_parser("attach")
    daemon_attach_parser.add_argument("--message", "-m", default=None)
    _add_handler(daemon_attach_parser, handle_attach)

    chat_parser = subparsers.add_parser("chat")
    chat_parser.add_argument("--message", "-m", default=None)
    chat_parser.add_argument("--require-daemon", action="store_true")
    _add_handler(chat_parser, handle_chat)

    attach_parser = subparsers.add_parser("attach")
    attach_parser.add_argument("--message", "-m", default=None)
    _add_handler(attach_parser, handle_attach)

    memory_parser = subparsers.add_parser("memory")
    memory_parser.set_defaults(handler=None, help_parser=memory_parser)
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    _add_handler(memory_subparsers.add_parser("list"), handle_memory_list)
    show_parser = memory_subparsers.add_parser("show")
    show_parser.add_argument("entry_id")
    _add_handler(show_parser, handle_memory_show)
    add_parser = memory_subparsers.add_parser("add")
    add_parser.add_argument("--type", required=True, choices=_memory_type_choices())
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--body", "--text", required=True)
    add_parser.add_argument("--tag", action="append", default=[])
    _add_handler(add_parser, handle_memory_add)
    edit_parser = memory_subparsers.add_parser("edit")
    edit_parser.add_argument("entry_id")
    edit_parser.add_argument("--title", default=None)
    edit_parser.add_argument("--body", "--text", default=None)
    edit_parser.add_argument("--tag", action="append", default=None)
    _add_handler(edit_parser, handle_memory_edit)
    delete_parser = memory_subparsers.add_parser("delete")
    delete_parser.add_argument("entry_id")
    _add_handler(delete_parser, handle_memory_delete)
    search_parser = memory_subparsers.add_parser("search")
    search_parser.add_argument("query")
    _add_handler(search_parser, handle_memory_search)
    _add_handler(memory_subparsers.add_parser("reindex"), handle_memory_reindex)

    return parser


def _add_handler(parser: argparse.ArgumentParser, handler: object) -> None:
    parser.set_defaults(handler=handler)


def handle_daemon_start(args: argparse.Namespace) -> int:
    result = lifecycle.start(args.project_root)
    print(_format_status(result))
    return 0 if result.running else 1


def handle_daemon_stop(args: argparse.Namespace) -> int:
    result = lifecycle.stop(args.project_root)
    print(_format_status(result))
    return 0 if not result.running else 1


def handle_daemon_status(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    print(_format_status(result))
    return 0 if result.running else 1


def handle_daemon_list(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    print(_format_daemon_list(result))
    return 0


def handle_default_entrypoint(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    if result.running:
        print(f"Using current daemon: {_format_status(result)}")
    else:
        print("Creating new daemon...")
        result = lifecycle.start(args.project_root)
        if not result.running:
            print(f"Failed to create daemon: {_format_status(result)}", file=sys.stderr)
            return 1
        print(f"Created daemon: {_format_status(result)}")
    if args.message is not None:
        return _send_chat(args.message, args.project_root)
    return _interactive_loop(lambda message: _send_chat(message, args.project_root), args.project_root)


def handle_daemon_logs(args: argparse.Namespace) -> int:
    paths = runtime_paths(args.project_root)
    try:
        print(paths.daemon_log_path.read_text(encoding="utf-8"), end="")
    except FileNotFoundError:
        print(f"No daemon log found at {paths.daemon_log_path}")
    return 0


def handle_chat(args: argparse.Namespace) -> int:
    if lifecycle.status(args.project_root).running:
        if args.message is not None:
            return _send_chat(args.message, args.project_root)
        return _interactive_loop(lambda message: _send_chat(message, args.project_root), args.project_root)
    if args.require_daemon:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_one_shot_chat(args.message, args.project_root)
    return _interactive_loop(lambda message: _send_one_shot_chat(message, args.project_root), args.project_root)


def handle_attach(args: argparse.Namespace) -> int:
    if not lifecycle.status(args.project_root).running:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_chat(args.message, args.project_root)
    return _interactive_loop(lambda message: _send_chat(message, args.project_root), args.project_root)


def handle_memory_list(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    entries = repo.list()
    if not entries:
        print("No memory entries.")
        return 0
    for entry in entries:
        print(_format_memory_summary(entry))
    return 0


def handle_memory_show(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        entry = repo.get(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    print(_format_memory_detail(entry))
    return 0


def handle_memory_add(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    entry = MemoryEntry(
        type=args.type,
        title=args.title,
        body=args.body,
        tags=list(args.tag),
    )
    repo.save(entry)
    repo.reindex()
    print(_format_memory_summary(entry))
    return 0


def handle_memory_edit(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        entry = repo.get(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    updated = entry.with_updates(
        title=args.title,
        body=args.body,
        tags=list(args.tag) if args.tag is not None else None,
    )
    repo.save(updated)
    repo.reindex()
    print(_format_memory_summary(updated))
    return 0


def handle_memory_delete(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        repo.delete(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    repo.reindex()
    print(f"Deleted memory entry: {args.entry_id}")
    return 0


def handle_memory_search(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    entries = repo.search(args.query)
    if not entries:
        print("No matching memory entries.")
        return 0
    for entry in entries:
        print(_format_memory_summary(entry))
    return 0


def handle_memory_reindex(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    index_path = repo.reindex()
    print(f"Rebuilt memory index: {index_path}")
    return 0


def _send_chat(message: str, project_root: Path | None) -> int:
    try:
        response = client.request(
            "chat",
            {"message": message},
            project_root=project_root,
            timeout=CHAT_REQUEST_TIMEOUT_SECONDS,
        )
    except client.DaemonConnectionError as exc:
        print(f"daemon request failed: {exc}", file=sys.stderr)
        return 1
    if response.status == "error":
        print(response.error or "daemon returned an error", file=sys.stderr)
        return 1
    reply = response.payload.get("reply")
    if isinstance(reply, str):
        print(reply)
        return 0
    print("daemon response did not include a reply", file=sys.stderr)
    return 1


def _interactive_loop(send_message: Callable[[str], int], project_root: Path | None) -> int:
    history_path = _load_interactive_history(project_root)
    print(_brand_banner())
    print("νSelf interactive mode. Type :q, :quit, or :exit to leave.")
    try:
        while True:
            try:
                line = input("NuSelf> ")
            except EOFError:
                print()
                return 0
            message = line.strip()
            if message == "":
                continue
            _remember_interactive_input(message)
            if message.startswith(":"):
                command_result = _handle_interactive_command(message)
                if command_result == "exit":
                    return 0
                continue
            print()
            result = send_message(message)
            print()
            if result != 0:
                return result
    finally:
        if history_path is not None:
            _write_interactive_history(history_path)


def _load_interactive_history(project_root: Path | None) -> Path | None:
    if readline is None:
        return None
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    history_path = paths.runtime_dir / "interactive_history"
    readline.clear_history()
    try:
        readline.read_history_file(str(history_path))
    except FileNotFoundError:
        pass
    except OSError:
        _load_plain_interactive_history(history_path)
    _dedupe_interactive_history()
    readline.set_history_length(1000)
    return history_path


def _load_plain_interactive_history(history_path: Path) -> None:
    if readline is None:
        return
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        if line != "":
            readline.add_history(line)


def _write_interactive_history(history_path: Path) -> None:
    if readline is None:
        return
    _dedupe_interactive_history()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    readline.write_history_file(str(history_path))


def _remember_interactive_input(message: str) -> None:
    if readline is None:
        return
    history_length = readline.get_current_history_length()
    if history_length > 0 and readline.get_history_item(history_length) == message:
        return
    readline.add_history(message)


def _dedupe_interactive_history() -> None:
    if readline is None:
        return
    history: list[str] = []
    previous: str | None = None
    for index in range(1, readline.get_current_history_length() + 1):
        item = readline.get_history_item(index)
        if item == previous:
            continue
        history.append(item)
        previous = item
    readline.clear_history()
    for item in history:
        readline.add_history(item)


def _send_one_shot_chat(message: str, project_root: Path | None) -> int:
    try:
        print(_one_shot_reply(message, project_root))
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


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


def _handle_interactive_command(command: str) -> str | None:
    if command in {":q", ":quit", ":exit"}:
        return "exit"
    print()
    print(_interactive_help(command))
    print()
    return None


def _interactive_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown interactive command: {command}")
    lines.extend(
        [
            "Interactive commands:",
            "  :q      exit",
            "  :quit   exit",
            "  :exit   exit",
        ]
    )
    return "\n".join(lines)


def _one_shot_reply(message: str, project_root: Path | None) -> str:
    return ChatAgent(project_root).respond(message, thread_id="default").reply


def _format_status(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return f"daemon {state} pid={pid} socket={status.socket_path}"


def _format_daemon_list(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return "\n".join(
        [
            "name status pid socket",
            f"local {state} {pid} {status.socket_path}",
        ]
    )


def _format_memory_summary(entry: MemoryEntry) -> str:
    tags = ",".join(entry.tags) if entry.tags else "-"
    return f"{entry.id} [{entry.type}] {entry.title} tags={tags} state={entry.review_state}"


def _format_memory_detail(entry: MemoryEntry) -> str:
    tags = ", ".join(entry.tags) if entry.tags else "-"
    return "\n".join(
        [
            f"id: {entry.id}",
            f"type: {entry.type}",
            f"title: {entry.title}",
            f"tags: {tags}",
            f"confidence: {entry.confidence}",
            f"privacy: {entry.privacy}",
            f"review_state: {entry.review_state}",
            f"created_at: {entry.created_at}",
            f"updated_at: {entry.updated_at}",
            "",
            entry.body,
        ]
    )


def _memory_type_choices() -> list[MemoryEntryType]:
    return [
        "source_note",
        "profile_fact",
        "belief",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
