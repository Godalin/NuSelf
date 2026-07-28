"""Transcript rendering, persistence, and clipboard helpers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli.repl.input import interactive_help
from nuself.cli.repl.registry import command_body
from nuself.config import runtime_paths
from nuself.logs import LogEvent
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.render import format_display_timestamp, render_log_event


class TranscriptSession(Protocol):
    """Session capabilities required by transcript export orchestration."""

    connected_at: datetime

    def start_index_for(
        self,
        project_root: Path | None,
        thread_id: str,
    ) -> int: ...

    def transcript_messages(
        self,
        project_root: Path | None,
        thread_id: str,
    ) -> list[tuple[int, str, str]]: ...

    def transcript_log_events(
        self,
        thread_id: str,
        *,
        include_all: bool,
    ) -> list[LogEvent]: ...

    def transcript_log_events_by_message(
        self,
        thread_id: str,
        *,
        include_all: bool,
    ) -> dict[int, list[LogEvent]]: ...

    def mark_transcript_exported(
        self,
        project_root: Path | None,
        thread_id: str,
    ) -> None: ...

    def thread_ids_with_unexported_messages(
        self,
        project_root: Path | None,
    ) -> list[str]: ...


def handle_interactive_export_command(
    command: str,
    project_root: Path | None,
    thread_id: str,
    session: TranscriptSession,
) -> str:
    """Parse one REPL export command and save the requested transcript."""

    body = command_body(command, "export")
    if body is None:
        return interactive_help(":export")
    copy_requested = True
    include_all_logs = False
    for arg in body.split():
        if arg == "all":
            include_all_logs = True
        elif arg == "noclip":
            copy_requested = False
        elif arg in {"--copy", "copy"}:
            copy_requested = True
        else:
            return interactive_help(":export")

    return save_interactive_transcript(
        project_root,
        thread_id,
        session,
        include_all_logs=include_all_logs,
        copy_requested=copy_requested,
        exported_at=datetime.now(UTC),
    )


def auto_save_interactive_transcripts(
    project_root: Path | None,
    session: TranscriptSession,
) -> None:
    """Save every thread with unexported messages on connection exit."""

    thread_ids = session.thread_ids_with_unexported_messages(project_root)
    if not thread_ids:
        return
    print()
    exported_at = datetime.now(UTC)
    for thread_id in thread_ids:
        print(
            save_interactive_transcript(
                project_root,
                thread_id,
                session,
                include_all_logs=False,
                copy_requested=False,
                exported_at=exported_at,
            )
        )


def save_interactive_transcript(
    project_root: Path | None,
    thread_id: str,
    session: TranscriptSession,
    *,
    include_all_logs: bool,
    copy_requested: bool,
    exported_at: datetime,
) -> str:
    """Persist one session transcript and optionally copy its contents."""

    try:
        start_index = session.start_index_for(project_root, thread_id)
        path, content = export_interactive_transcript(
            project_root,
            thread_id=thread_id,
            start_index=start_index,
            connected_at=session.connected_at,
            exported_at=exported_at,
            messages=session.transcript_messages(project_root, thread_id),
            log_events=session.transcript_log_events(
                thread_id,
                include_all=include_all_logs,
            ),
            log_events_by_message=session.transcript_log_events_by_message(
                thread_id,
                include_all=include_all_logs,
            ),
            include_all_logs=include_all_logs,
        )
    except ValueError as exc:
        return f"Error: {diagnostic_exception_message(exc)}"

    session.mark_transcript_exported(project_root, thread_id)
    lines = [f"Saved transcript: {path}"]
    if copy_requested:
        copied, reason = copy_text_to_clipboard(content)
        if copied:
            lines.append("Copied transcript to clipboard.")
        else:
            lines.append(f"Clipboard copy failed: {reason}")
    return "\n".join(lines)


def export_interactive_transcript(
    project_root: Path | None,
    *,
    thread_id: str,
    start_index: int,
    connected_at: datetime,
    exported_at: datetime,
    messages: list[tuple[int, str, str]] | None = None,
    log_events: list[LogEvent] | None = None,
    log_events_by_message: dict[int, list[LogEvent]] | None = None,
    include_all_logs: bool = False,
) -> tuple[Path, str]:
    paths = runtime_paths(project_root)
    if messages is None:
        thread = ThreadStore(project_root).load(thread_id)
        messages = thread_messages_from_index(thread, start_index)
    if not messages:
        raise ValueError("no chat messages in this connection yet")

    export_dir = paths.private_root / "transcripts"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"chat-{_safe_filename_component(thread_id)}-"
        f"{_compact_timestamp(connected_at)}-{_compact_timestamp(exported_at)}.md"
    )
    path = export_dir / filename
    content = render_chat_transcript(
        thread_id=thread_id,
        connected_at=connected_at,
        exported_at=exported_at,
        messages=messages,
        log_events=log_events or [],
        log_events_by_message=log_events_by_message or {},
        include_all_logs=include_all_logs,
    )
    path.write_text(content, encoding="utf-8")
    return path, content


def thread_messages_from_index(
    thread: ThreadState, start_index: int
) -> list[tuple[int, str, str]]:
    messages: list[tuple[int, str, str]] = []
    for offset, message in enumerate(thread.messages):
        index = thread.message_start_index + offset
        if index >= start_index:
            messages.append((index, message.role, message.content))
    return messages


def render_chat_transcript(
    *,
    thread_id: str,
    connected_at: datetime,
    exported_at: datetime,
    messages: list[tuple[int, str, str]],
    log_events: list[LogEvent],
    log_events_by_message: dict[int, list[LogEvent]],
    include_all_logs: bool,
) -> str:
    lines = [
        "# NuSelf Chat Transcript",
        "",
        f"- Thread: `{thread_id}`",
        f"- Connected: {format_display_timestamp(connected_at)}",
        f"- Exported: {format_display_timestamp(exported_at)}",
        f"- Logs: {'all' if include_all_logs else 'share'}",
        "",
    ]
    for index, role, content in messages:
        label = "User" if role == "user" else "NuSelf"
        lines.extend([
            f"## {index}. {label}",
            "",
            _normalize_transcript_body(content),
            "",
        ])
        message_log_events = log_events_by_message.get(index, [])
        if message_log_events:
            lines.extend(["### Logs", ""])
            for event in message_log_events:
                lines.extend(_render_transcript_log_event(event))
                lines.append("")
    if log_events:
        lines.extend(["## Internal Process Logs", ""])
        for event in log_events:
            lines.extend(_render_transcript_log_event(event))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_transcript_log_event(event: LogEvent) -> list[str]:
    return [f"> {line}" if line else ">" for line in render_log_event(event, color=False).splitlines()]


def _normalize_transcript_body(content: str) -> str:
    body = content.strip()
    if body == "":
        return "_(empty)_"
    return _escape_markdown_fences(body)


def _escape_markdown_fences(text: str) -> str:
    lines = text.splitlines()
    longest_backtick_run = 0
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("```"):
            continue
        run = len(stripped) - len(stripped.lstrip("`"))
        longest_backtick_run = max(longest_backtick_run, run)
    if longest_backtick_run == 0:
        return text
    fence = "`" * (longest_backtick_run + 1)
    normalized_lines: list[str] = []
    for line in lines:
        leading_width = len(line) - len(line.lstrip())
        leading = line[:leading_width]
        stripped = line[leading_width:]
        if stripped.startswith("`" * longest_backtick_run):
            normalized_lines.append(f"{leading}{fence}{stripped[longest_backtick_run:]}")
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def is_shareable_transcript_log(event: LogEvent) -> bool:
    if event.component == "chat" and event.event == "service_tool_called":
        return True
    if event.component == "persona":
        return event.event in {
            "persona_summary",
            "host_discussion_decision",
            "persona_discussion",
            "persona_discussion_step",
        }
    if event.component == "reflection":
        return event.event in {"persona_discussion", "cycle_completed", "cycle_discussion_rejected"}
    return False


def copy_text_to_clipboard(text: str) -> tuple[bool, str]:
    command = _clipboard_command()
    if command is None:
        return False, "no supported clipboard command found"
    try:
        subprocess.run(command, input=text, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, diagnostic_exception_message(exc)
    return True, ""


def _clipboard_command() -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("pbcopy") is not None:
        return ["pbcopy"]
    if shutil.which("wl-copy") is not None:
        return ["wl-copy"]
    if shutil.which("xclip") is not None:
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel") is not None:
        return ["xsel", "--clipboard", "--input"]
    return None


def _safe_filename_component(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    return cleaned.strip("-") or "thread"


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
