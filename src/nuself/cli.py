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
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEntryType, MemoryEvidence
from nuself.memory.curator import MemoryCurator
from nuself.memory.intake import MemoryIntakeAgent
from nuself.memory.optimizer import MemoryOptimizer, MemoryOptimizerSettings
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryNotFound,
    MemoryEntryRepository,
)

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_MEMORY_PREVIEW_LIMIT = 8


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
    preview_parser = memory_subparsers.add_parser("preview")
    preview_parser.add_argument("--limit", type=int, default=DEFAULT_MEMORY_PREVIEW_LIMIT)
    _add_handler(preview_parser, handle_memory_preview)
    show_parser = memory_subparsers.add_parser("show")
    show_parser.add_argument("entry_id")
    _add_handler(show_parser, handle_memory_show)
    add_parser = memory_subparsers.add_parser("add")
    add_parser.add_argument("--type", choices=_memory_type_choices())
    add_parser.add_argument("--title", default=None)
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
    _add_handler(memory_subparsers.add_parser("update"), handle_memory_update)
    optimize_parser = memory_subparsers.add_parser("optimize")
    optimize_parser.add_argument("--limit", type=int, default=50)
    _add_handler(optimize_parser, handle_memory_optimize)
    candidate_parser = memory_subparsers.add_parser("candidate")
    candidate_parser.set_defaults(handler=None, help_parser=candidate_parser)
    candidate_subparsers = candidate_parser.add_subparsers(dest="candidate_command")
    candidate_list_parser = candidate_subparsers.add_parser("list")
    candidate_list_parser.add_argument("--all", action="store_true")
    _add_handler(candidate_list_parser, handle_memory_candidate_list)
    candidate_show_parser = candidate_subparsers.add_parser("show")
    candidate_show_parser.add_argument("candidate_id")
    _add_handler(candidate_show_parser, handle_memory_candidate_show)
    candidate_accept_parser = candidate_subparsers.add_parser("accept")
    candidate_accept_parser.add_argument("candidate_id")
    _add_handler(candidate_accept_parser, handle_memory_candidate_accept)
    candidate_reject_parser = candidate_subparsers.add_parser("reject")
    candidate_reject_parser.add_argument("candidate_id")
    _add_handler(candidate_reject_parser, handle_memory_candidate_reject)
    candidate_edit_parser = candidate_subparsers.add_parser("edit")
    candidate_edit_parser.add_argument("candidate_id")
    candidate_edit_parser.add_argument("--title", default=None)
    candidate_edit_parser.add_argument("--body", "--text", default=None)
    candidate_edit_parser.add_argument("--tag", action="append", default=None)
    candidate_edit_parser.add_argument("--observed-at", default=None)
    candidate_edit_parser.add_argument("--valid-from", default=None)
    candidate_edit_parser.add_argument("--valid-until", default=None)
    candidate_edit_parser.add_argument("--temporal-note", default=None)
    _add_handler(candidate_edit_parser, handle_memory_candidate_edit)
    candidate_merge_parser = candidate_subparsers.add_parser("merge")
    candidate_merge_parser.add_argument("candidate_id")
    candidate_merge_parser.add_argument("entry_id")
    _add_handler(candidate_merge_parser, handle_memory_candidate_merge)
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


def handle_memory_preview(args: argparse.Namespace) -> int:
    print(_format_memory_preview(args.project_root, args.limit))
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
    inferred = MemoryIntakeAgent(args.project_root).infer(
        body=args.body,
        title=args.title,
        memory_type=args.type,
        tags=list(args.tag),
    )
    entry = MemoryEntry(
        type=inferred.type,
        title=inferred.title,
        body=inferred.body,
        tags=list(inferred.tags),
        confidence=inferred.confidence,
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


def handle_memory_update(args: argparse.Namespace) -> int:
    result = MemoryCurator(args.project_root).run_once()
    print(f"Memory curator: {result.summary()} log={result.log_path}")
    return 0


def handle_memory_optimize(args: argparse.Namespace) -> int:
    settings = MemoryOptimizerSettings(memory_limit=args.limit)
    result = MemoryOptimizer(args.project_root, settings=settings).run_once()
    print(f"Memory optimizer: {result.summary()} log={result.log_path}")
    return 0


def handle_memory_candidate_list(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    candidates = repo.list(include_reviewed=args.all)
    if not candidates:
        print("No memory candidates.")
        return 0
    for candidate in candidates:
        print(_format_memory_candidate_summary(candidate))
    return 0


def handle_memory_candidate_show(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        candidate = repo.get(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    print(_format_memory_candidate_detail(candidate))
    return 0


def handle_memory_candidate_accept(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        entry = repo.accept(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Accepted memory candidate: {args.candidate_id} -> {entry.id}")
    return 0


def handle_memory_candidate_reject(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        repo.reject(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    print(f"Rejected memory candidate: {args.candidate_id}")
    return 0


def handle_memory_candidate_edit(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        candidate = repo.get(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    updated = candidate.with_updates(
        title=args.title,
        body=args.body,
        tags=list(args.tag) if args.tag is not None else None,
        observed_at=args.observed_at,
        valid_from=args.valid_from,
        valid_until=args.valid_until,
        temporal_note=args.temporal_note,
    )
    repo.save(updated)
    print(_format_memory_candidate_summary(updated))
    return 0


def handle_memory_candidate_merge(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        entry = repo.merge(args.candidate_id, args.entry_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Merged memory candidate: {args.candidate_id} -> {entry.id}")
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
        memory_update = response.payload.get("memory_update")
        if isinstance(memory_update, str) and memory_update != "":
            print(f"[memory] {memory_update}")
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
                command_result = _handle_interactive_command(message, project_root)
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
        _run_memory_curator(project_root)


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
        _run_memory_curator(project_root)
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _run_memory_curator(project_root: Path | None) -> None:
    try:
        result = MemoryCurator(project_root).run_once()
    except RuntimeError as exc:
        print(f"[memory] curator failed: {exc}", file=sys.stderr)
        return
    if result.changed:
        print(f"[memory] {result.summary()}")


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


def _handle_interactive_command(command: str, project_root: Path | None) -> str | None:
    if command in {":q", ":quit", ":exit"}:
        return "exit"
    if command in {":memory", ":mem"}:
        print()
        print(_format_memory_preview(project_root))
        print()
        return None
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
            "  :memory preview memory entries",
            "  :mem    preview memory entries",
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
            f"observed_at: {entry.observed_at or '-'}",
            f"valid_from: {entry.valid_from or '-'}",
            f"valid_until: {entry.valid_until or '-'}",
            f"temporal_note: {entry.temporal_note or '-'}",
            "evidence:",
            *_format_evidence_lines(entry.evidence),
            "",
            entry.body,
        ]
    )


def _format_memory_candidate_summary(candidate: MemoryCandidate) -> str:
    tags = ",".join(candidate.tags) if candidate.tags else "-"
    observed = candidate.observed_at or "-"
    return (
        f"{candidate.id} [{candidate.review_state}] {candidate.action} {candidate.type} "
        f"{candidate.title} tags={tags} observed_at={observed}"
    )


def _format_memory_candidate_detail(candidate: MemoryCandidate) -> str:
    tags = ", ".join(candidate.tags) if candidate.tags else "-"
    return "\n".join(
        [
            f"id: {candidate.id}",
            f"action: {candidate.action}",
            f"type: {candidate.type}",
            f"title: {candidate.title}",
            f"tags: {tags}",
            f"confidence: {candidate.confidence}",
            f"privacy: {candidate.privacy}",
            f"review_state: {candidate.review_state}",
            f"reason: {candidate.reason or '-'}",
            f"target_entry_id: {candidate.target_entry_id or '-'}",
            f"created_at: {candidate.created_at}",
            f"updated_at: {candidate.updated_at}",
            f"reviewed_at: {candidate.reviewed_at or '-'}",
            f"observed_at: {candidate.observed_at or '-'}",
            f"valid_from: {candidate.valid_from or '-'}",
            f"valid_until: {candidate.valid_until or '-'}",
            f"temporal_note: {candidate.temporal_note or '-'}",
            "evidence:",
            *_format_evidence_lines(candidate.evidence),
            "",
            candidate.body,
        ]
    )


def _format_evidence_lines(evidence_items: list[MemoryEvidence]) -> list[str]:
    if not evidence_items:
        return ["  -"]
    lines: list[str] = []
    for evidence in evidence_items:
        observed = evidence.observed_at or "-"
        summary = f" summary={evidence.summary}" if evidence.summary else ""
        lines.append(f"  - {evidence.source_type} {evidence.source_ref} observed_at={observed}{summary}")
    return lines or ["  -"]


def _format_memory_preview(project_root: Path | None, limit: int = DEFAULT_MEMORY_PREVIEW_LIMIT) -> str:
    normalized_limit = max(limit, 1)
    entries = MemoryEntryRepository(project_root).list()
    if not entries:
        return "No memory entries."
    shown = entries[:normalized_limit]
    lines = [f"Memory preview ({len(shown)}/{len(entries)}):"]
    for entry in shown:
        body = _compact_text(entry.body, 96)
        tags = ",".join(entry.tags) if entry.tags else "-"
        lines.append(
            f"- {entry.id} [{entry.type}] {entry.title} "
            f"tags={tags} confidence={entry.confidence:.2f} state={entry.review_state}"
        )
        if body != "":
            lines.append(f"  {body}")
    if len(entries) > normalized_limit:
        lines.append(f"... {len(entries) - normalized_limit} more. Use `nuself memory list` or `nuself memory preview --limit N`.")
    return "\n".join(lines)


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _memory_type_choices() -> list[MemoryEntryType]:
    return [
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
