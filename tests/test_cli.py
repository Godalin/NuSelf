from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess
import sys
import threading
import tomllib
from typing import Protocol, cast

import pytest

from nuself import cli
from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.cli import build_parser, main
from nuself.daemon.client import DaemonConnectionError
from nuself.daemon.protocol import DaemonResponse
from nuself.daemon.lifecycle import DaemonStatus
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence
from nuself.llm import ChatMessage


def _mock_status(project_root: Path) -> DaemonStatus:
    return DaemonStatus(
        running=True, pid=123, socket_path=Path("/dev/null"), pid_path=Path("/dev/null")
    )
from nuself.domain.profile import ProfileItem
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.logs import LogEvent, log_context, read_log_events, write_log_event
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.reason.service import ReasonService
from nuself.trace.service import TraceQueryService


class CaptureResult(Protocol):
    out: str
    err: str


class CaptureFixture(Protocol):
    def readouterr(self) -> CaptureResult: ...


class MonkeyPatchFixture(Protocol):
    def setattr(self, target: str, value: object) -> None: ...
    def delenv(self, name: str, raising: bool = True) -> None: ...


class FakeChangedCuratorResult:
    changed = True
    log_path = Path("memory.log")

    def summary(self) -> str:
        return "processed=2 created=1 updated=0 ignored=0"


class FakeChangedCurator:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root

    def run_once(self) -> FakeChangedCuratorResult:
        return FakeChangedCuratorResult()


def test_chat_uses_one_shot_when_daemon_is_missing(tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture) -> None:
    result = main(["--project-root", str(tmp_path), "chat", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "LLM API is not configured yet" in captured.out
    assert "Last message: hello" in captured.out
    assert (tmp_path / "private" / "threads" / "default.json").is_file()


def test_one_shot_chat_runs_memory_curator_after_reply(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("nuself.cli.MemoryCurator", FakeChangedCurator)

    result = main(["--project-root", str(tmp_path), "chat", "--message", "remember this preference"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Last message: remember this preference" in captured.out
    assert "[memory] processed=2 created=1 updated=0 ignored=0" in captured.out


def test_assistant_reply_prints_plain_text_when_stdout_is_not_tty(
    capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    print_assistant_reply = cast(Callable[[str], None], getattr(cli, "_print_assistant_reply"))

    print_assistant_reply("**hello**")

    captured = capsys.readouterr()
    assert captured.out == "**hello**\n"


def test_assistant_reply_uses_rich_renderer_when_stdout_is_tty(monkeypatch: MonkeyPatchFixture) -> None:
    rendered: list[str] = []
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("nuself.cli._render_assistant_reply_rich", rendered.append)
    print_assistant_reply = cast(Callable[[str], None], getattr(cli, "_print_assistant_reply"))

    print_assistant_reply("**hello**")

    assert rendered == ["**hello**"]


def test_chat_without_message_enters_one_shot_interactive_mode(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("hello\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "┌────┐" in captured.out
    assert "interactive mode" in captured.out
    assert "LLM API is not configured yet" in captured.out
    assert "Last message: hello" in captured.out
    history_path = tmp_path / "private" / "runtime" / "interactive_history"
    assert history_path.is_file()
    content = history_path.read_text(encoding="utf-8")
    assert "+hello" in content


def test_unknown_interactive_command_shows_help_and_keeps_session_open(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":bad\nhello\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Unknown interactive command: :bad" in captured.out
    assert "Interactive commands:" in captured.out
    assert ":mem, :m                  preview memory entries" in captured.out
    assert "LLM API is not configured yet" in captured.out
    assert "Last message: hello" in captured.out


def test_interactive_memory_command_shows_preview(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--type",
            "belief",
            "--title",
            "Clarity",
            "--body",
            "State assumptions explicitly.",
        ]
    )
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", _TextInput(":mem\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "1/1 entries shown." in captured.out
    assert "Clarity" in captured.out
    assert "State assumptions explicitly." in captured.out


def test_interactive_memory_search_uses_readable_rows(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="belief",
            title="Readable memory",
            body="Terminal memory output should be easy to scan.",
            tags=["display"],
            review_state="reviewed",
        )
    )
    monkeypatch.setattr("sys.stdin", _TextInput(":mem search terminal\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[memory] state=reviewed type=belief" in captured.out
    assert "Readable memory" in captured.out
    assert "tags=[display]" in captured.out
    assert "Terminal memory output should be easy to scan." in captured.out


def test_interactive_memory_show_uses_readable_detail(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    entry = MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="belief",
            title="Readable detail",
            body="Detail views can show the full memory body.",
            tags=["display"],
            evidence=[MemoryEvidence(source_type="thread", source_ref="thread:default:1-2", summary="chat")],
        )
    )
    monkeypatch.setattr("sys.stdin", _TextInput(f":mem show {entry.id}\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[memory] state=draft type=belief" in captured.out
    assert f"id={entry.id}" in captured.out
    assert "evidence:" in captured.out
    assert "Detail views can show the full memory body." in captured.out


def test_interactive_memory_candidates_profile_and_sources(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    MemoryCandidateRepository(tmp_path).save(
        MemoryCandidate(type="belief", title="Candidate display", body="Candidate body.", reason="inspect")
    )
    ProfileItemRepository(tmp_path).save(
        ProfileItem(type="profile_fact", title="Profile display", body="Prefers readable output.")
    )
    source_path = tmp_path / "source.md"
    source_path.write_text("# Source Display\n\nA readable source paragraph.", encoding="utf-8")
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()
    monkeypatch.setattr(
        "sys.stdin",
        _TextInput(":mem review\n:mem profile readable\n:mem sources\n:q\n"),
    )

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[candidate] [0] state=pending" in captured.out
    assert "Candidate display" in captured.out
    assert "[profile] type=profile_fact" in captured.out
    assert "Profile display" in captured.out
    assert "[source]" in captured.out
    assert "Source Display" in captured.out


def test_interactive_status_command_shows_daemon_status(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":dev status\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "daemon stopped" in captured.out
    assert "daemon stopped pid=- socket=" in captured.out
    assert "\n\nNuSelf> " not in captured.out.split("daemon stopped", maxsplit=1)[1]


def test_interactive_logs_command_shows_recent_activity(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    write_log_event("chat", "turn_completed", "chat turn completed", project_root=tmp_path)
    monkeypatch.setattr("sys.stdin", _TextInput(":dev logs\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[chat] turn_completed" in captured.out
    assert "  chat turn completed" in captured.out


def test_interactive_turn_prints_activity_events(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("hello\n:q\n"))
    monkeypatch.setattr("nuself.cli._last_header_thread", "")
    monkeypatch.setattr("nuself.cli._last_header_status", "")

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "\nNuSelf:\n\nLLM API is not configured yet." in captured.out
    assert "[chat] one_shot_chat_completed" not in captured.out
    assert "LLM API is not configured yet" in captured.out
    assert "Last message: hello\n[daemon] session status=one-shot thread=default" in captured.out
    assert "Last message: hello\n\n[daemon] session status=one-shot thread=default" not in captured.out


def test_interactive_turn_prints_activity_events_while_waiting(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("default"))
    printed = threading.Event()
    original_print_events = cast(Callable[[list[LogEvent]], None], getattr(cli, "_print_interactive_activity_events"))

    def fake_print_events(events: list[LogEvent]) -> None:
        printed.set()
        original_print_events(events)

    def fake_send(message: str, thread_id: str, turn_id: str | None) -> cli.InteractiveChatResult:
        assert turn_id is not None
        write_log_event(
            "chat",
            "service_tool_called",
            "args: {}\nresult: live progress before reply",
            project_root=tmp_path,
            thread_id=thread_id,
            turn_id=turn_id,
            status="completed",
            metadata={"service_component": "memory", "tool": "memory_search"},
        )
        if not printed.wait(1.0):
            return cli.InteractiveChatResult(code=1, reply="log was not printed live")
        return cli.InteractiveChatResult(code=0, reply="final reply")

    monkeypatch.setattr("nuself.cli._print_interactive_activity_events", fake_print_events)
    monkeypatch.setattr("nuself.cli.INTERACTIVE_LOG_POLL_INTERVAL_SECONDS", 0.01)

    session = cli.InteractiveSession(connected_at=cli.datetime.now(cli.UTC))
    send_turn = cast(Callable[..., int], getattr(cli, "_send_interactive_chat_turn"))
    result = send_turn(
        fake_send,
        tmp_path,
        "default",
        "hello",
        session,
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "Logs:\n[chat] [memory] service_tool_called" in captured.out
    assert "NuSelf:\n\nfinal reply" in captured.out
    assert captured.out.index("[chat] [memory] service_tool_called") < captured.out.index("NuSelf:\n\nfinal reply")


def test_interactive_turn_hides_background_activity_events(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("default"))

    def fake_send(message: str, thread_id: str, turn_id: str | None) -> cli.InteractiveChatResult:
        assert turn_id is not None
        write_log_event(
            "reflection",
            "cycle_completed",
            "background reflection finished",
            project_root=tmp_path,
            thread_id=thread_id,
            status="completed",
        )
        write_log_event(
            "reasoning",
            "step_created",
            "background reasoning advanced",
            project_root=tmp_path,
            thread_id=thread_id,
            status="completed",
        )
        write_log_event(
            "chat",
            "service_tool_called",
            "args: {}\nresult: visible service result",
            project_root=tmp_path,
            thread_id=thread_id,
            turn_id=turn_id,
            status="completed",
            metadata={"service_component": "memory", "tool": "memory_search"},
        )
        return cli.InteractiveChatResult(code=0, reply="final reply")

    session = cli.InteractiveSession(connected_at=cli.datetime.now(cli.UTC))
    send_turn = cast(Callable[..., int], getattr(cli, "_send_interactive_chat_turn"))
    result = send_turn(
        fake_send,
        tmp_path,
        "default",
        "hello",
        session,
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "background reflection finished" not in captured.out
    assert "background reasoning advanced" not in captured.out
    assert "[chat] [memory] service_tool_called" in captured.out
    assert "visible service result" in captured.out
    assert "NuSelf:\n\nfinal reply" in captured.out
    captured_events = session.transcript_log_events("default", include_all=True)
    assert [event.component for event in captured_events] == ["chat"]


def test_interactive_daemon_timeout_retries_and_preserves_logs(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    calls = 0
    turn_ids: list[object] = []

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal calls
        calls += 1
        payload_dict = cast(dict[str, object], payload)
        turn_id = payload_dict.get("turn_id")
        turn_ids.append(turn_id)
        if calls == 1:
            write_log_event(
                "persona",
                "persona_summary",
                "builder_self: first attempt reached persona discussion",
                project_root=project_root,
                thread_id="default",
                turn_id=turn_id if isinstance(turn_id, str) else None,
                status="retryable timeout",
            )
            raise DaemonConnectionError("timed out")
        return DaemonResponse(request_id="r1", status="ok", payload={"reply": "daemon reply"})

    monkeypatch.setattr("sys.stdin", _TextInput("hello\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert calls == 2
    assert len(set(turn_ids)) == 1
    assert isinstance(turn_ids[0], str)
    assert "daemon request failed: timed out" in captured.err
    assert "Retrying message after failed attempt (2/2)..." in captured.out
    assert "builder_self: first attempt reached persona discussion" in captured.out
    assert "daemon reply" in captured.out


def test_interactive_daemon_application_error_does_not_retry(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    calls = 0

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal calls
        calls += 1
        payload_dict = cast(dict[str, object], payload)
        turn_id = payload_dict.get("turn_id")
        write_log_event(
            "chat",
            "turn_failed",
            "daemon chat turn failed",
            project_root=project_root,
            thread_id="default",
            turn_id=turn_id if isinstance(turn_id, str) else None,
            status="error",
            error="graph failed <- root cause",
        )
        return DaemonResponse.fail("r1", "graph failed <- root cause")

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("sys.stdin", _TextInput("hello\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert calls == 1
    assert "graph failed <- root cause" not in captured.err
    assert "error=\"graph failed <- root cause\"" in captured.out
    assert "Retrying message after failed attempt" not in captured.out
    assert "Message failed after retry" not in captured.err
    assert captured.out.count("[chat] turn_failed") == 1


def test_interactive_export_saves_connection_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    copied: list[str] = []

    def fake_copy(text: str) -> tuple[bool, str]:
        copied.append(text)
        return True, ""

    monkeypatch.setattr("sys.stdin", _TextInput("first message\n:export\nsecond message\n:export\n:q\n"))
    monkeypatch.setattr("nuself.cli._copy_text_to_clipboard", fake_copy)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-default-*.md"))
    assert len(exports) == 2
    first_export = exports[0].read_text(encoding="utf-8")
    second_export = exports[1].read_text(encoding="utf-8")
    assert "first message" in first_export
    assert "second message" not in first_export
    assert "first message" in second_export
    assert "second message" in second_export
    assert "- Thread: `default`" in second_export
    assert len(copied) == 2
    assert "second message" in copied[-1]


def test_interactive_export_copy_copies_saved_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    copied: list[str] = []

    def fake_copy(text: str) -> tuple[bool, str]:
        copied.append(text)
        return True, ""

    monkeypatch.setattr("sys.stdin", _TextInput("share this\n:export\n:q\n"))
    monkeypatch.setattr("nuself.cli._copy_text_to_clipboard", fake_copy)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    assert "Copied transcript to clipboard." in captured.out
    assert len(copied) == 1
    assert "share this" in copied[0]
    assert "# NuSelf Chat Transcript" in copied[0]


def test_interactive_export_noclip_skips_clipboard(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    copied: list[str] = []

    def fake_copy(text: str) -> tuple[bool, str]:
        copied.append(text)
        return True, ""

    monkeypatch.setattr("sys.stdin", _TextInput("do not copy\n:e noclip\n:q\n"))
    monkeypatch.setattr("nuself.cli._copy_text_to_clipboard", fake_copy)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    assert "Copied transcript to clipboard." not in captured.out
    assert copied == []


def test_interactive_export_all_includes_all_logs(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("include logs\n:e all noclip\nsecond turn\n:e all noclip\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    capsys.readouterr()

    assert result == 0
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-default-*.md"))
    assert len(exports) == 2
    content = exports[-1].read_text(encoding="utf-8")
    assert "- Logs: all" in content
    assert "### Logs" in content
    assert "> [chat] one_shot_chat_completed status=ok thread=default turn=turn-" in content
    assert ">   one-shot chat turn completed" in content
    assert "```json" not in content
    assert "```text" not in content
    first_reply_index = content.index("## 1. NuSelf")
    first_logs_index = content.index("### Logs")
    second_reply_index = content.index("## 2. NuSelf")
    assert first_reply_index < first_logs_index < second_reply_index


def test_render_transcript_share_includes_service_tool_logs() -> None:
    render_transcript = cast(Callable[..., str], getattr(cli, "_render_chat_transcript"))
    service_log = LogEvent(
        time="2026-05-19T10:00:00Z",
        level="info",
        component="chat",
        event="service_tool_called",
        message='args: {"limit": 3}\nresult: Pending reflection ideas:\n[1] One idea',
        thread_id="default",
        status="completed",
        metadata={"service_component": "reflection", "tool": "reflection_list_pending"},
    )

    content = render_transcript(
        thread_id="default",
        connected_at=cli.datetime.now(cli.UTC),
        exported_at=cli.datetime.now(cli.UTC),
        messages=[(0, "user", "any reflections?"), (1, "assistant", "One idea.")],
        log_events=[],
        log_events_by_message={1: [service_log]},
        include_all_logs=False,
    )

    assert "> [chat] [reflection] service_tool_called status=completed thread=default tool=reflection_list_pending" in content
    assert '>   args: {"limit": 3}' in content
    assert ">   result: Pending reflection ideas:" in content


def test_interactive_export_normalizes_markdown_body_fences() -> None:
    render_transcript = cast(Callable[..., str], getattr(cli, "_render_chat_transcript"))
    content = render_transcript(
        thread_id="default",
        connected_at=cli.datetime.now(cli.UTC),
        exported_at=cli.datetime.now(cli.UTC),
        messages=[(0, "user", "show fence"), (1, "assistant", "```python\nprint('ok')\n```")],
        log_events=[],
        log_events_by_message={},
        include_all_logs=False,
    )

    assert "````python\nprint('ok')\n````" in content
    assert content.endswith("\n")
    assert not content.endswith("\n\n")


def test_interactive_quit_auto_saves_unexported_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("autosave this\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    assert "Copied transcript to clipboard." not in captured.out
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-default-*.md"))
    assert len(exports) == 1
    assert "autosave this" in exports[0].read_text(encoding="utf-8")


def test_interactive_eof_auto_saves_unexported_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("autosave eof\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-default-*.md"))
    assert len(exports) == 1
    assert "autosave eof" in exports[0].read_text(encoding="utf-8")


def test_interactive_keyboard_interrupt_auto_saves_unexported_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    inputs = ["autosave interrupt"]

    def fake_input(_prompt: str) -> str:
        if inputs:
            return inputs.pop(0)
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", fake_input)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 130
    assert "Saved transcript:" in captured.out
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-default-*.md"))
    assert len(exports) == 1
    assert "autosave interrupt" in exports[0].read_text(encoding="utf-8")


def test_interactive_quit_auto_saves_all_threads(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("first thread\n:thread beta\nsecond thread\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out.count("Saved transcript:") == 2
    exports = sorted((tmp_path / "private" / "transcripts").glob("chat-*.md"))
    assert len(exports) == 2
    contents = "\n".join(path.read_text(encoding="utf-8") for path in exports)
    assert "first thread" in contents
    assert "second thread" in contents
    assert "Thread: `default`" in contents
    assert "Thread: `beta`" in contents


def test_interactive_history_skips_consecutive_duplicates(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("same\nsame\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    capsys.readouterr()

    assert result == 0
    history_path = tmp_path / "private" / "runtime" / "interactive_history"
    content = history_path.read_text(encoding="utf-8")
    assert content.count("+same") == 1


def test_daemon_status_reports_missing_daemon(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "status"])
    captured = capsys.readouterr()

    assert result == 1
    assert "daemon stopped" in captured.out


def test_incomplete_daemon_command_shows_subcommand_help(capsys: CaptureFixture) -> None:
    result = main(["daemon"])
    captured = capsys.readouterr()

    assert result == 0
    assert "usage: nuself daemon" in captured.out
    assert "start" in captured.out
    assert "status" in captured.out
    assert "attach" in captured.out


def test_default_entrypoint_uses_existing_daemon_with_message(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    def fake_send(message: str, project_root: Path | None) -> int:
        print(f"sent {message}")
        return 0

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli._send_chat", fake_send)

    result = main(["--project-root", str(tmp_path), "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Using current daemon:" in captured.out
    assert "pid=123" in captured.out
    assert "sent hello" in captured.out


def test_default_entrypoint_interactive_omits_redundant_startup_preamble(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)

    result = main(["--project-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert result == 0
    assert "Using current daemon:" not in captured.out
    assert "Tip:" not in captured.out
    assert "νSelf interactive mode. Type :help for commands, :q to quit." in captured.out
    assert "[daemon] session status=running thread=default" in captured.out


def test_default_entrypoint_creates_daemon_when_missing(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    stopped = DaemonStatus(
        running=False,
        pid=None,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    running = DaemonStatus(
        running=True,
        pid=456,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return stopped

    def fake_start(project_root: Path | None) -> DaemonStatus:
        return running

    def fake_send(message: str, project_root: Path | None) -> int:
        print(f"sent {message}")
        return 0

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.lifecycle.start", fake_start)
    monkeypatch.setattr("nuself.cli._send_chat", fake_send)

    result = main(["--project-root", str(tmp_path), "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Starting NuSelf daemon..." in captured.out
    assert "Daemon started:" in captured.out
    assert "pid=456" in captured.out
    assert "sent hello" in captured.out


def test_daemon_chat_uses_long_timeout(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    captured_timeout = 0.0
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal captured_timeout
        captured_timeout = timeout
        return DaemonResponse(
            request_id="r1",
            status="ok",
            payload={"reply": "daemon reply"},
        )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "attach", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "daemon reply" in captured.out
    assert captured_timeout == cli.CHAT_REQUEST_TIMEOUT_SECONDS


def test_daemon_chat_uses_configured_request_timeout(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    private_dir = tmp_path / "private"
    private_dir.mkdir(parents=True)
    (private_dir / "config.yaml").write_text(
        "chat:\n  request_timeout_seconds: 600\n",
        encoding="utf-8",
    )
    captured_timeout = 0.0
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal captured_timeout
        captured_timeout = timeout
        return DaemonResponse(
            request_id="r1",
            status="ok",
            payload={"reply": "daemon reply"},
        )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "attach", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "daemon reply" in captured.out
    assert captured_timeout == 600


def test_daemon_chat_prints_memory_update(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        return DaemonResponse(
            request_id="r1",
            status="ok",
            payload={
                "reply": "daemon reply",
                "memory_update": "processed=2 created=1 updated=0 ignored=0",
            },
        )

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "attach", "--message", "remember this"])
    captured = capsys.readouterr()

    assert result == 0
    assert "daemon reply" in captured.out
    assert "[memory] processed=2 created=1 updated=0 ignored=0" in captured.out


def test_daemon_chat_connection_error_is_reported(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    daemon_status = DaemonStatus(
        running=True,
        pid=123,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_request(
        request_type: object,
        payload: object | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        raise DaemonConnectionError("timed out")

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return daemon_status

    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.client.request", fake_request)

    result = main(["--project-root", str(tmp_path), "attach", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 1
    assert "daemon request failed: timed out" in captured.err


def test_daemon_list_reports_local_daemon(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "list"])
    captured = capsys.readouterr()

    assert result == 0
    assert "name status pid socket" in captured.out
    assert "local stopped -" in captured.out


def test_logs_command_renders_structured_events(tmp_path: Path, capsys: CaptureFixture) -> None:
    write_log_event(
        "chat",
        "turn_completed",
        "chat turn completed",
        project_root=tmp_path,
        thread_id="default",
        status="ok",
        metadata={"message_body": "must not be written by callers"},
    )
    write_log_event("memory", "curator_changed", "memory curator changed durable memory", project_root=tmp_path)

    result = main(["--project-root", str(tmp_path), "dev", "logs", "--component", "chat", "--tail", "5", "--no-color"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[chat] turn_completed" in captured.out
    assert "  chat turn completed" in captured.out
    assert "thread=default" in captured.out
    assert "[memory]" not in captured.out


def test_logs_command_can_render_json(tmp_path: Path, capsys: CaptureFixture) -> None:
    write_log_event("daemon", "started", "daemon started", project_root=tmp_path)

    result = main(["--project-root", str(tmp_path), "dev", "logs", "--component", "daemon", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"component": "daemon"' in captured.out
    assert '"event": "started"' in captured.out


def test_log_context_applies_runtime_ownership_fields(tmp_path: Path) -> None:
    with log_context(thread_id="default", request_id="req-1", turn_id="turn-1", source="test"):
        event = write_log_event("chat", "turn_started", "chat turn started", project_root=tmp_path)
        nested = write_log_event("chat", "tool", "tool ran", project_root=tmp_path, turn_id="turn-2")

    events = read_log_events(project_root=tmp_path, component="chat")

    assert event.thread_id == "default"
    assert event.request_id == "req-1"
    assert event.turn_id == "turn-1"
    assert event.source == "test"
    assert nested.thread_id == "default"
    assert nested.request_id == "req-1"
    assert nested.turn_id == "turn-2"
    assert events[-2].turn_id == "turn-1"
    assert events[-1].turn_id == "turn-2"


def test_interactive_activity_cursor_does_not_replay_seen_events(tmp_path: Path) -> None:
    write_log_event("chat", "turn_started", "old turn", project_root=tmp_path)
    from nuself.logs import InteractiveLogCursor

    cursor = InteractiveLogCursor.from_project(tmp_path)

    write_log_event("chat", "turn_completed", "new turn", project_root=tmp_path, turn_id="turn-new")

    from nuself.cli import _interactive_activity_events  # pyright: ignore[reportPrivateUsage]

    first_read = _interactive_activity_events(tmp_path, cursor, turn_id="turn-new")
    second_read = _interactive_activity_events(tmp_path, cursor)

    assert [event.event for event in first_read] == ["turn_completed"]
    assert second_read == []


def test_read_log_events_tolerates_legacy_daemon_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "private" / "logs" / "daemon.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("plain daemon output\n", encoding="utf-8")

    events = read_log_events(project_root=tmp_path, component="daemon")

    assert len(events) == 1
    assert events[0].event == "legacy"
    assert events[0].message == "plain daemon output"


def test_daemon_attach_requires_running_daemon(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "attach", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 1
    assert "NuSelf daemon is not running." in captured.err


def test_incomplete_memory_command_shows_subcommand_help(capsys: CaptureFixture) -> None:
    result = main(["memory"])
    captured = capsys.readouterr()

    assert result == 0
    assert "usage: nuself memory" in captured.out
    assert "list" in captured.out
    assert "List memory entries with visible indexes." in captured.out
    assert "preview" in captured.out
    assert "Show the memory preview used by chat context." in captured.out
    assert "review" in captured.out
    assert "Review pending memory candidates." in captured.out
    assert "reindex" in captured.out


def test_memory_group_help_describes_nested_commands(capsys: CaptureFixture) -> None:
    expected = {
        ("memory", "review"): [
            "accept",
            "Accept review candidates by ID, index, or selection.",
            "reject",
            "Reject review candidates by ID, index, or selection.",
        ],
        ("memory", "source"): [
            "ingest",
            "Ingest a source document.",
            "extract",
            "Extract memory candidates from one source document.",
        ],
        ("memory", "profile"): [
            "list",
            "List profile entries with visible indexes.",
            "delete",
            "Delete one profile entry by ID or visible index.",
        ],
        ("memory", "graph"): [
            "nodes",
            "List graph nodes.",
            "closure",
            "Show reachable graph context from one node.",
        ],
    }

    for argv, snippets in expected.items():
        result = main(list(argv))
        captured = capsys.readouterr()

        assert result == 0
        assert f"usage: nuself {' '.join(argv)}" in captured.out
        for snippet in snippets:
            assert snippet in captured.out


def test_command_group_help_describes_subcommands(capsys: CaptureFixture) -> None:
    expected = {
        ("daemon",): [
            "start",
            "Start the background daemon.",
            "logs",
            "Show daemon logs.",
        ],
        ("thread",): [
            "open",
            "Open or create a thread for chat.",
            "archived",
            "List archived conversation threads.",
        ],
        ("inbox",): [
            "reflection",
            "Review reflection candidates.",
            "notify",
            "Manage notification outbox entries.",
        ],
        ("inbox", "reflection"): [
            "promote",
            "Promote one reflection into a reason thread.",
            "organize",
            "Merge similar pending reflection entries.",
        ],
        ("inbox", "notify"): [
            "send",
            "Send one pending notification now.",
            "clear",
            "Clear sent, failed, and dismissed notifications.",
        ],
        ("reason",): [
            "start",
            "Start a new reasoning thread.",
            "watch",
            "Watch reasoning threads for new steps.",
        ],
        ("trace",): [
            "search",
            "Search thought traces.",
            "reindex",
            "Rebuild thought trace indexes.",
        ],
        ("persona",): [
            "list",
            "List synthesized persona snapshots.",
            "delete",
            "Delete one persona snapshot.",
        ],
        ("dev",): [
            "health",
            "Run local health checks.",
            "eval",
            "Run evaluation fixtures.",
        ],
    }

    for argv, snippets in expected.items():
        result = main(list(argv))
        captured = capsys.readouterr()

        assert result == 0
        assert f"usage: nuself {' '.join(argv)}" in captured.out
        for snippet in snippets:
            assert snippet in captured.out


def test_memory_preview_limits_entries(tmp_path: Path, capsys: CaptureFixture) -> None:
    for title in ["First", "Second"]:
        main(
            [
                "--project-root",
                str(tmp_path),
                "memory",
                "add",
                "--type",
                "belief",
                "--title",
                title,
                "--body",
                f"{title} body with enough text to preview.",
            ]
        )
        capsys.readouterr()

    result = main(["--project-root", str(tmp_path), "memory", "preview", "--limit", "1"])
    captured = capsys.readouterr()

    assert result == 0
    assert "1/2 entries shown." in captured.out
    assert "to see more." in captured.out


def test_memory_preview_uses_list_record_style_without_indexes(tmp_path: Path, capsys: CaptureFixture) -> None:
    MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="belief",
            title="Preview style",
            body="Memory preview should use the same record body style as list.",
            tags=["cli"],
            review_state="reviewed",
            confidence=0.8,
        )
    )

    result = main(["--project-root", str(tmp_path), "memory", "preview"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[memory] state=reviewed type=belief" in captured.out
    assert "[memory] [0]" not in captured.out
    assert "  Preview style" in captured.out
    assert "  Memory preview should use the same record body style as list." in captured.out


def test_memory_update_defers_without_agent_decision(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="We need automatic memory curation."),
                ThreadMessage(role="assistant", content="I will summarize conversations into memory."),
            ],
        )
    )

    result = main(["--project-root", str(tmp_path), "memory", "update"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Memory curator: processed=0 created=0 updated=0 ignored=0" in captured.out
    assert main_memory_preview(tmp_path) == ""


def test_memory_optimize_defers_without_agent_decision(tmp_path: Path, capsys: CaptureFixture) -> None:
    MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="belief",
            title="Messy memory",
            body="This entry needs later optimization.",
        )
    )

    result = main(["--project-root", str(tmp_path), "memory", "optimize"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Memory optimizer: reviewed=0 updated=0 deleted=0 ignored=0" in captured.out
    assert "Messy memory" in main_memory_preview(tmp_path)


def test_memory_add_list_show_delete(tmp_path: Path, capsys: CaptureFixture) -> None:
    add_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--type",
            "belief",
            "--title",
            "Clarity",
            "--body",
            "State assumptions explicitly.",
            "--tag",
            "style",
        ]
    )
    add_output = capsys.readouterr().out
    entry_id = add_output.split()[3].removeprefix("id=")

    list_result = main(["--project-root", str(tmp_path), "memory", "list"])
    list_output = capsys.readouterr().out

    show_result = main(["--project-root", str(tmp_path), "memory", "show", "0"])
    show_output = capsys.readouterr().out

    delete_result = main(["--project-root", str(tmp_path), "memory", "delete", "0"])
    delete_output = capsys.readouterr().out

    assert add_result == 0
    assert list_result == 0
    assert show_result == 0
    assert delete_result == 0
    assert "[memory] [0]" in list_output
    assert "Clarity" in list_output
    assert "State assumptions explicitly." in show_output
    assert f"Deleted memory entry: {entry_id}" in delete_output


def test_memory_add_infers_type_without_manual_type(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    class FakeIntakeLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return (
                '{"type":"preference","title":"Terse CLI summaries",'
                '"tags":["cli"],"confidence":0.8,"importance":0.6}'
            )

    def fake_default_llm(project_root: Path | None = None) -> FakeIntakeLLM:
        return FakeIntakeLLM()

    monkeypatch.setattr("nuself.memory.intake.default_llm", fake_default_llm)
    add_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--body",
            "I prefer terse CLI summaries with concrete next steps.",
        ]
    )
    add_output = capsys.readouterr().out
    entry_id = add_output.split()[3].removeprefix("id=")

    entry = MemoryEntryRepository(tmp_path).get(entry_id)

    assert add_result == 0
    assert entry.type == "preference"
    assert entry.title == "Terse CLI summaries"
    assert entry.tags == ["cli"]
    assert entry.body == "I prefer terse CLI summaries with concrete next steps."


def test_memory_add_supports_goal_and_concept_types(tmp_path: Path, capsys: CaptureFixture) -> None:
    goal_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--type",
            "goal",
            "--title",
            "Finish memory system",
            "--body",
            "Complete the typed memory workflow.",
        ]
    )
    capsys.readouterr()
    concept_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--type",
            "concept",
            "--title",
            "Temporal memory",
            "--body",
            "Memory that preserves real-world time.",
        ]
    )
    capsys.readouterr()

    entries = MemoryEntryRepository(tmp_path).list()
    types = {entry.type for entry in entries}

    assert goal_result == 0
    assert concept_result == 0
    assert types == {"goal", "concept"}


def test_memory_candidate_review_flow_accepts_temporal_candidate(tmp_path: Path, capsys: CaptureFixture) -> None:
    candidate = MemoryCandidateRepository(tmp_path).save(
        MemoryCandidate(
            type="belief",
            title="Temporal memory",
            body="Memory should preserve when a view was observed.",
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref="thread:default:4-6",
                    summary="Discussed thought evolution.",
                    observed_at="2026-05-07",
                )
            ],
            observed_at="2026-05-07",
            temporal_note="The user asked for visible thought evolution.",
        )
    )

    list_result = main(["--project-root", str(tmp_path), "memory", "review", "list"])
    list_output = capsys.readouterr().out
    show_result = main(["--project-root", str(tmp_path), "memory", "review", "show", "0"])
    show_output = capsys.readouterr().out
    accept_result = main(["--project-root", str(tmp_path), "memory", "review", "accept", "0"])
    accept_output = capsys.readouterr().out

    entries = MemoryEntryRepository(tmp_path).list()

    assert list_result == 0
    assert show_result == 0
    assert accept_result == 0
    assert "[candidate] [0]" in list_output
    assert "Temporal memory" in list_output
    assert f"id={candidate.id}" in show_output
    assert "thread:thread:default:4-6" in show_output
    assert "Accepted memory candidate:" in accept_output
    assert entries[0].observed_at == "2026-05-07"
    assert entries[0].evidence[0].source_ref == "thread:default:4-6"
    assert entries[0].temporal_note == "The user asked for visible thought evolution."


def test_memory_candidate_accepts_batch_index_selection(tmp_path: Path, capsys: CaptureFixture) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    created = [
        repo.save(MemoryCandidate(type="belief", title=f"Candidate {i}", body=f"Body {i}."))
        for i in range(5)
    ]
    listed = repo.list()
    expected_ids = {listed[1].id, listed[3].id, listed[4].id}

    result = main(["--project-root", str(tmp_path), "memory", "review", "accept", "1,3-4"])
    output = capsys.readouterr().out

    accepted_ids = {entry.id for entry in MemoryEntryRepository(tmp_path).list()}
    remaining_ids = {candidate.id for candidate in repo.list()}
    assert result == 0
    assert output.count("Accepted memory candidate:") == 3
    assert expected_ids.isdisjoint(remaining_ids)
    assert len(accepted_ids) == 3
    assert {candidate.id for candidate in created}.issuperset(expected_ids)


def test_memory_candidate_rejects_batch_index_selection(tmp_path: Path, capsys: CaptureFixture) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    created = [
        repo.save(MemoryCandidate(type="belief", title=f"Candidate {i}", body=f"Body {i}."))
        for i in range(4)
    ]
    listed = repo.list()
    rejected_ids = {listed[0].id, listed[2].id, listed[3].id}
    pending_id = listed[1].id

    result = main(["--project-root", str(tmp_path), "memory", "review", "reject", "0,2-3"])
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("Rejected memory candidate:") == 3
    assert repo.get(pending_id).review_state == "pending"
    assert {candidate.id for candidate in created}.issuperset(rejected_ids)
    for candidate_id in rejected_ids:
        assert repo.get(candidate_id).review_state == "rejected"


def test_memory_candidate_batch_index_selection_rejects_whitespace(
    tmp_path: Path, capsys: CaptureFixture
) -> None:
    repo = MemoryCandidateRepository(tmp_path)
    repo.save(MemoryCandidate(type="belief", title="Candidate", body="Body."))

    result = main(["--project-root", str(tmp_path), "memory", "review", "accept", "0, 1"])
    output = capsys.readouterr().err

    assert result == 1
    assert "Invalid memory candidate index selection" in output


def test_memory_candidate_edit_merge_and_reject(tmp_path: Path, capsys: CaptureFixture) -> None:
    entry = MemoryEntryRepository(tmp_path).save(
        MemoryEntry(type="belief", title="Old timing idea", body="Memory has timestamps.")
    )
    candidate_repo = MemoryCandidateRepository(tmp_path)
    merge_candidate = candidate_repo.save(
        MemoryCandidate(
            type="belief",
            title="Timing candidate",
            body="Memory timing should show how views change.",
        )
    )
    reject_candidate = candidate_repo.save(
        MemoryCandidate(type="episode", title="Reject me", body="Not useful.")
    )

    edit_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "review",
            "edit",
            merge_candidate.id,
            "--title",
            "Thought timeline",
            "--observed-at",
            "2026-05-07",
            "--temporal-note",
            "Edited during review.",
        ]
    )
    edit_output = capsys.readouterr().out
    merge_result = main(
        ["--project-root", str(tmp_path), "memory", "review", "merge", merge_candidate.id, entry.id]
    )
    merge_output = capsys.readouterr().out
    reject_result = main(
        ["--project-root", str(tmp_path), "memory", "review", "reject", reject_candidate.id]
    )
    reject_output = capsys.readouterr().out

    merged = MemoryEntryRepository(tmp_path).get(entry.id)

    assert edit_result == 0
    assert merge_result == 0
    assert reject_result == 0
    assert "Thought timeline" in edit_output
    assert "Merged memory candidate:" in merge_output
    assert "Rejected memory candidate:" in reject_output
    assert merged.title == "Thought timeline"
    assert merged.observed_at == "2026-05-07"
    assert candidate_repo.get(reject_candidate.id).review_state == "rejected"


def test_memory_stats_and_filtered_search(tmp_path: Path, capsys: CaptureFixture) -> None:
    MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="belief",
            title="Temporal belief",
            body="Memory should include time.",
            tags=["memory"],
            review_state="reviewed",
            observed_at="2026-05-07",
        )
    )
    MemoryEntryRepository(tmp_path).save(
        MemoryEntry(
            type="episode",
            title="Unrelated episode",
            body="Something else happened.",
            tags=["event"],
        )
    )
    MemoryCandidateRepository(tmp_path).save(
        MemoryCandidate(type="belief", title="Pending belief", body="Candidate body.")
    )

    stats_result = main(["--project-root", str(tmp_path), "memory", "stats"])
    stats_output = capsys.readouterr().out
    search_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "search",
            "time",
            "--type",
            "belief",
            "--tag",
            "memory",
            "--review-state",
            "reviewed",
            "--observed-from",
            "2026-05-01",
        ]
    )
    search_output = capsys.readouterr().out

    assert stats_result == 0
    assert search_result == 0
    assert "entries_total: 2" in stats_output
    assert "pending_candidates: 1" in stats_output
    assert "avg_importance: 0.50" in stats_output
    assert "max_importance: 0.50" in stats_output
    assert "avg_importance_by_type: belief=0.50, episode=0.50" in stats_output
    assert "entries_by_type: belief=1, episode=1" in stats_output
    assert "Temporal belief" in search_output
    assert "Unrelated episode" not in search_output


def test_memory_relations_lists_and_filters_derived_index(tmp_path: Path, capsys: CaptureFixture) -> None:
    repo = MemoryEntryRepository(tmp_path)
    old = repo.save(MemoryEntry(type="belief", title="Old model", body="Closed categories."))
    related = repo.save(MemoryEntry(type="concept", title="Graph retrieval", body="Relations expand recall."))
    current = repo.save(
        MemoryEntry(
            type="belief",
            title="New model",
            body="Open descriptors.",
            relations={"supersedes": [old.id], "related_to": [related.id]},
        )
    )

    list_result = main(["--project-root", str(tmp_path), "memory", "relations"])
    list_output = capsys.readouterr().out
    filter_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "relations",
            "--relation",
            "related_to",
            "--source-id",
            current.id,
        ]
    )
    filter_output = capsys.readouterr().out

    assert list_result == 0
    assert filter_result == 0
    assert f"{current.id} --supersedes-> {old.id}" in list_output
    assert f"{current.id} --related_to-> {related.id}" in list_output
    assert "Graph retrieval" in filter_output
    assert "Old model" not in filter_output


def test_memory_graph_lists_nodes_and_edges(tmp_path: Path, capsys: CaptureFixture) -> None:
    repo = MemoryEntryRepository(tmp_path)
    target = repo.save(MemoryEntry(type="concept", title="Graph node", body="A graph target."))
    source = repo.save(
        MemoryEntry(
            type="belief",
            title="Graph edge",
            body="A graph source.",
            relations={"related_to": [target.id]},
        )
    )

    nodes_result = main(["--project-root", str(tmp_path), "memory", "graph", "nodes", "--type", "concept"])
    nodes_output = capsys.readouterr().out
    edges_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "graph",
            "edges",
            "--relation",
            "related_to",
            "--source-id",
            source.id,
        ]
    )
    edges_output = capsys.readouterr().out
    search_result = main(["--project-root", str(tmp_path), "memory", "graph", "search", "target"])
    search_output = capsys.readouterr().out

    assert nodes_result == 0
    assert edges_result == 0
    assert search_result == 0
    assert target.id in nodes_output
    assert "Graph node" in nodes_output
    assert source.id not in nodes_output
    assert f"{source.id}:related_to:{target.id}" in edges_output
    assert f"{source.id} --related_to-> {target.id}" in edges_output
    assert "Nodes:" in search_output
    assert "Edges:" in search_output
    assert target.id in search_output
    assert f"{source.id}:related_to:{target.id}" in search_output


def test_memory_source_ingest_list_show_and_chunks(tmp_path: Path, capsys: CaptureFixture) -> None:
    source_path = tmp_path / "essay.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Source Essay",
                "date: 2026-05-07",
                "tags: [mirror]",
                "origin: notebook",
                "---",
                "# Heading",
                "",
                "A durable source paragraph.",
            ]
        ),
        encoding="utf-8",
    )

    ingest_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "source",
            "ingest",
            str(source_path),
            "--tag",
            "imported",
            "--privacy",
            "shareable",
        ]
    )
    ingest_output = capsys.readouterr().out
    list_result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[2].removeprefix("id=")
    show_result = main(["--project-root", str(tmp_path), "memory", "source", "show", "0"])
    show_output = capsys.readouterr().out
    chunks_result = main(["--project-root", str(tmp_path), "memory", "source", "chunks", "0"])
    chunks_output = capsys.readouterr().out

    assert ingest_result == 0
    assert list_result == 0
    assert show_result == 0
    assert chunks_result == 0
    assert "Source ingest: documents=1 chunks=1" in ingest_output
    assert "[source] [0]" in list_output
    assert "Source Essay" in list_output
    assert "tags=[mirror, imported]" in list_output
    assert "shareable" in list_output
    assert "origin=notebook" in show_output
    assert "source_date=2026-05-07" in show_output
    assert f"source:{source_id}:0" in chunks_output
    assert "A durable source paragraph." in chunks_output


def test_memory_source_search_and_reindex(tmp_path: Path, capsys: CaptureFixture) -> None:
    source_path = tmp_path / "searchable.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Searchable Source",
                "tags: [retrieval]",
                "---",
                "This paragraph contains durable citation material.",
            ]
        ),
        encoding="utf-8",
    )
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()

    search_result = main(
        ["--project-root", str(tmp_path), "memory", "source", "search", "durable citation", "--limit", "3"]
    )
    search_output = capsys.readouterr().out
    reindex_result = main(["--project-root", str(tmp_path), "memory", "reindex"])
    reindex_output = capsys.readouterr().out

    assert search_result == 0
    assert reindex_result == 0
    assert "source:" in search_output
    assert "Searchable Source" in search_output
    assert "durable citation material" in search_output
    assert "Rebuilt memory index:" in reindex_output
    assert "Rebuilt relation index:" in reindex_output
    assert "Rebuilt symbolic graph:" in reindex_output
    assert "Rebuilt source index:" in reindex_output
    assert "Rebuilt profile index:" in reindex_output
    assert (tmp_path / "private" / "derived" / "memory_index.json").is_file()
    assert (tmp_path / "private" / "derived" / "relation_index.json").is_file()
    assert (tmp_path / "private" / "derived" / "symbolic_graph.json").is_file()
    assert (tmp_path / "private" / "derived" / "source_index.json").is_file()
    assert (tmp_path / "private" / "derived" / "profile_index.json").is_file()


def test_memory_source_extract_creates_reviewable_profile_candidate(
    tmp_path: Path, capsys: CaptureFixture
) -> None:
    source_path = tmp_path / "profile-source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Profile Source",
                "tags: [mirror]",
                "---",
                "The user prefers concise, doc-aligned answers.",
            ]
        ),
        encoding="utf-8",
    )
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()

    list_result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    capsys.readouterr()

    extract_result = main(["--project-root", str(tmp_path), "memory", "source", "extract", "0"])
    extract_output = capsys.readouterr().out
    candidate_list_result = main(["--project-root", str(tmp_path), "memory", "review", "list"])
    candidate_list_output = capsys.readouterr().out

    assert list_result == 0
    assert extract_result == 0
    assert candidate_list_result == 0
    assert "Extracted source candidates:" in extract_output
    assert "profile_fact" in candidate_list_output


def test_memory_source_delete_cascades_profile_items(tmp_path: Path, capsys: CaptureFixture) -> None:
    source_path = tmp_path / "profile-source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Profile Source",
                "tags: [mirror]",
                "---",
                "The user prefers concise, doc-aligned answers.",
            ]
        ),
        encoding="utf-8",
    )
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()
    list_result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[2].removeprefix("id=")
    main(["--project-root", str(tmp_path), "memory", "source", "extract", source_id])
    capsys.readouterr()

    delete_result = main(["--project-root", str(tmp_path), "memory", "source", "delete", "0"])
    delete_output = capsys.readouterr().out
    profile_list_result = main(["--project-root", str(tmp_path), "memory", "profile", "list"])
    profile_list_output = capsys.readouterr().out

    assert list_result == 0
    assert delete_result == 0
    assert "Deleted source document:" in delete_output
    assert profile_list_result == 0
    assert "No profile items." in profile_list_output


def test_memory_profile_delete_removes_item_and_reindexes(tmp_path: Path, capsys: CaptureFixture) -> None:
    source_path = tmp_path / "profile-source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Profile Source",
                "tags: [mirror]",
                "---",
                "The user prefers concise, doc-aligned answers.",
            ]
        ),
        encoding="utf-8",
    )
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()
    list_result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[2].removeprefix("id=")
    main(["--project-root", str(tmp_path), "memory", "source", "extract", source_id])
    capsys.readouterr()
    candidate_repo = MemoryCandidateRepository(tmp_path)
    candidate_id = candidate_repo.list()[0].id
    main(["--project-root", str(tmp_path), "memory", "review", "accept", candidate_id])
    capsys.readouterr()
    profile_repo = ProfileItemRepository(tmp_path)
    assert profile_repo.list()

    delete_result = main(["--project-root", str(tmp_path), "memory", "profile", "delete", "0"])
    delete_output = capsys.readouterr().out
    profile_list_result = main(["--project-root", str(tmp_path), "memory", "profile", "list"])
    profile_list_output = capsys.readouterr().out

    assert list_result == 0
    assert delete_result == 0
    assert "Deleted profile item:" in delete_output
    assert profile_list_result == 0
    assert "No profile items." in profile_list_output


def test_memory_profile_search_filters_and_query(tmp_path: Path, capsys: CaptureFixture) -> None:
    repo = ProfileItemRepository(tmp_path)
    repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli", "style"],
            source_refs=["source:abc:0"],
            observed_at="2026-05-07",
            valid_from="2026-05-07",
        )
    )
    repo.save(
        ProfileItem(
            type="profile_fact",
            title="Long-form output",
            body="Likes detailed summaries.",
            tags=["docs"],
            source_refs=["source:def:0"],
            observed_at="2026-05-08",
        )
    )

    search_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "profile",
            "search",
            "concise",
            "--type",
            "profile_fact",
            "--tag",
            "style",
            "--observed-from",
            "2026-05-01",
            "--valid-on",
            "2026-05-07",
        ]
    )
    search_output = capsys.readouterr().out

    assert search_result == 0
    assert "Concise output" in search_output
    assert "Long-form output" not in search_output


class _TextInput:
    def __init__(self, text: str) -> None:
        self._lines = text.splitlines(keepends=True)

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)


def main_memory_preview(project_root: Path) -> str:
    from nuself.memory.repository import MemoryEntryRepository

    return "\n".join(entry.title for entry in MemoryEntryRepository(project_root).list())



def test_thread_list_shows_thread_ids(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("alpha"))
    ThreadStore(tmp_path).save(ThreadState.empty("beta"))

    result = main(["--project-root", str(tmp_path), "thread", "list"])
    captured = capsys.readouterr()

    assert result == 0
    assert "alpha" in captured.out
    assert "beta" in captured.out


def test_thread_create_makes_new_thread(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "new", "new-thread"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Created thread: new-thread" in captured.out
    assert "new-thread.json" in [p.name for p in (tmp_path / "private" / "threads").glob("*.json")]


def test_thread_create_fails_when_thread_exists(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("existing"))

    result = main(["--project-root", str(tmp_path), "thread", "new", "existing"])
    captured = capsys.readouterr()

    assert result == 1
    assert "already exists" in captured.err


def test_thread_rename_moves_thread(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("old"))

    result = main(["--project-root", str(tmp_path), "thread", "rename", "old", "new"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Renamed thread: old -> new" in captured.out
    assert ThreadStore(tmp_path).list() == ["new"]


def test_thread_rename_fails_when_target_exists(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("a"))
    ThreadStore(tmp_path).save(ThreadState.empty("b"))

    result = main(["--project-root", str(tmp_path), "thread", "rename", "a", "b"])
    captured = capsys.readouterr()

    assert result == 1
    assert "already exists" in captured.err


def test_thread_branch_copies_messages(tmp_path: Path, capsys: CaptureFixture) -> None:
    store = ThreadStore(tmp_path)
    store.save(
        ThreadState(
            thread_id="source",
            summary="summary",
            messages=[
                ThreadMessage(role="user", content="a"),
                ThreadMessage(role="assistant", content="b"),
            ],
            message_start_index=0,
            next_message_index=2,
        )
    )

    result = main(["--project-root", str(tmp_path), "thread", "branch", "source", "fork"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Branched thread: source -> fork" in captured.out
    fork = store.load("fork")
    assert len(fork.messages) == 2
    assert fork.thread_id == "fork"


def test_thread_branch_at_index(tmp_path: Path, capsys: CaptureFixture) -> None:
    store = ThreadStore(tmp_path)
    store.save(
        ThreadState(
            thread_id="source",
            messages=[
                ThreadMessage(role="user", content="a"),
                ThreadMessage(role="assistant", content="b"),
                ThreadMessage(role="user", content="c"),
            ],
            message_start_index=5,
            next_message_index=8,
        )
    )

    result = main(["--project-root", str(tmp_path), "thread", "branch", "source", "fork", "--index", "2"])

    assert result == 0
    fork = store.load("fork")
    assert len(fork.messages) == 2
    assert fork.next_message_index == 7


def test_thread_archive_moves_to_subdir(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("old"))

    result = main(["--project-root", str(tmp_path), "thread", "archive", "old"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Archived thread: old" in captured.out
    assert ThreadStore(tmp_path).list() == []
    archived = tmp_path / "private" / "threads" / "archived" / "old.json"
    assert archived.exists()


def test_thread_delete_removes_thread(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("gone"))

    result = main(["--project-root", str(tmp_path), "thread", "delete", "gone"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Deleted thread: gone" in captured.out
    assert ThreadStore(tmp_path).list() == []
    assert not (tmp_path / "private" / "threads" / "gone.json").exists()


def test_thread_delete_fails_when_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "delete", "missing"])
    captured = capsys.readouterr()

    assert result == 1
    assert "Error: thread not found: missing" in captured.err


def test_thread_unarchive_restores_thread(tmp_path: Path, capsys: CaptureFixture) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("old"))
    store.archive("old")

    result = main(["--project-root", str(tmp_path), "thread", "unarchive", "old"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Unarchived thread: old" in captured.out
    assert store.list() == ["old"]
    assert not (tmp_path / "private" / "threads" / "archived" / "old.json").exists()


def test_thread_unarchive_fails_when_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "unarchive", "missing"])
    captured = capsys.readouterr()

    assert result == 1
    assert "Error: archived thread not found: missing" in captured.err


def test_thread_archived_lists_archived_threads(tmp_path: Path, capsys: CaptureFixture) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("alpha"))
    store.save(ThreadState.empty("beta"))
    store.archive("alpha")

    result = main(["--project-root", str(tmp_path), "thread", "archived"])
    captured = capsys.readouterr()

    assert result == 0
    assert "alpha" in captured.out
    assert "beta" not in captured.out


def test_thread_archived_shows_none_when_empty(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "archived"])
    captured = capsys.readouterr()

    assert result == 0
    assert "No archived threads." in captured.out


def test_open_existing_thread_shows_thread_in_header(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("focus"))
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))

    result = main(["--project-root", str(tmp_path), "thread", "open", "focus"])
    captured = capsys.readouterr()

    assert result == 0
    assert "thread=focus" in captured.out


def test_open_missing_thread_fails(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "open", "missing"])
    captured = capsys.readouterr()

    assert result == 1
    assert "Thread not found: missing" in captured.err


def test_open_create_makes_thread_and_enters_repl(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))

    result = main(["--project-root", str(tmp_path), "thread", "open", "new-thread", "--create"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Created thread: new-thread" in captured.out
    assert "thread=new-thread" in captured.out
    assert "new-thread.json" in [p.name for p in (tmp_path / "private" / "threads").glob("*.json")]


def test_open_with_message_sends_then_enters_repl(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("focus"))
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))

    result = main(["--project-root", str(tmp_path), "thread", "open", "focus", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "LLM API is not configured yet" in captured.out
    assert "thread=focus" in captured.out


def test_notify_list_show_send_dismiss(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    entry = outbox.add(
        OutboxEntry(
            id="test-001",
            title="Test Notification",
            body="This is a test.",
            status="pending",
            idempotency_key="test-001-key",
        )
    )

    list_result = main(["--project-root", str(tmp_path), "inbox", "notify", "list"])
    list_output = capsys.readouterr().out

    show_result = main(["--project-root", str(tmp_path), "inbox", "notify", "show", entry.id])
    show_output = capsys.readouterr().out

    send_result = main(["--project-root", str(tmp_path), "inbox", "notify", "send", entry.id])
    send_output = capsys.readouterr().out

    dismiss_result = main(["--project-root", str(tmp_path), "inbox", "notify", "dismiss", entry.id])
    dismiss_output = capsys.readouterr().out

    assert list_result == 0
    assert show_result == 0
    assert send_result == 0
    assert dismiss_result == 0
    assert entry.id in list_output
    assert "Test Notification" in list_output
    assert "pending" in list_output
    assert entry.id in show_output
    assert "Test Notification" in show_output
    assert f"Sent: {entry.id}" in send_output
    assert f"Dismissed: {entry.id}" in dismiss_output


def test_notify_show_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "show", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_send_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "send", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_dismiss_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "dismiss", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_show_by_numeric_handle(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Second", body="B2", status="pending", idempotency_key="k2"))

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "show", "1"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Second" in output


def test_notify_dismiss_by_numeric_handle(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Second", body="B2", status="pending", idempotency_key="k2"))

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "dismiss", "0"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Dismissed: e1" in output


def test_notify_numeric_handle_out_of_range(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "show", "5"])
    output = capsys.readouterr().err
    assert result == 1
    assert "Invalid notification index" in output


def test_notify_list_empty(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "list"])
    output = capsys.readouterr().out
    assert result == 0
    assert "No outbox entries." in output


def test_notify_list_filters_by_status(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="Pending", body="B", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Sent", body="B", status="sent", idempotency_key="k2"))
    outbox.add(OutboxEntry(id="e3", title="Failed", body="B", status="failed", idempotency_key="k3"))

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "list", "--status", "pending"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Pending" in output
    assert "Sent" not in output
    assert "Failed" not in output


def test_notify_show_renders_detail(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="e1",
            title="Test Title",
            body="Test Body",
            status="pending",
            idempotency_key="k1",
            deep_link="nuself://thread/default",
        )
    )
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "show", "e1"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Test Title" in output
    assert "Test Body" in output
    assert "pending" in output
    assert "nuself://thread/default" in output
    assert "idempotency_key=k1" in output


def test_notify_stats_counts(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="A", body="B", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="A", body="B", status="sent", idempotency_key="k2"))
    outbox.add(OutboxEntry(id="e3", title="A", body="B", status="sent", idempotency_key="k3"))
    outbox.add(OutboxEntry(id="e4", title="A", body="B", status="failed", idempotency_key="k4"))

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "stats"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Total:      4" in output
    assert "Pending:    1" in output
    assert "Sent:       2" in output
    assert "Failed:     1" in output
    assert "Dismissed:  0" in output


def test_repl_notify_list_shows_all(tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="Pending", body="B", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Sent", body="B", status="sent", idempotency_key="k2"))

    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify list\n:q\n"))
    result = main(["--project-root", str(tmp_path), "chat"])
    output = capsys.readouterr().out
    assert result == 0
    assert "All notifications:" in output
    assert "Pending" in output
    assert "Sent" in output


def test_repl_notify_show_detail(tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="Test", body="Body", status="pending", idempotency_key="k1"))

    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify show e1\n:q\n"))
    result = main(["--project-root", str(tmp_path), "chat"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Test" in output
    assert "Body" in output


def test_open_with_deep_link_parses_thread_id(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        ["--project-root", str(tmp_path), "thread", "open", "--deep-link", "nuself://thread/my-thread"]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "Thread not found: my-thread" in captured.err


def test_open_with_deep_link_and_message(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))
    result = main(
        [
            "--project-root",
            str(tmp_path),
            "thread",
            "open",
            "--deep-link",
            "nuself://thread/my-thread?message=hello",
            "--create",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Created thread: my-thread" in captured.out


def test_open_with_invalid_deep_link(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        ["--project-root", str(tmp_path), "thread", "open", "--deep-link", "https://example.com"]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "Invalid deep link" in captured.err


def test_open_with_new_thread_deep_link(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))
    result = main(
        [
            "--project-root",
            str(tmp_path),
            "thread",
            "open",
            "--deep-link",
            "nuself://new-thread?title=proactive-thread&message=hello%20there",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Created thread: proactive-thread" in captured.out


def test_status_command_shows_daemon_threads_and_notifications(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "dev", "status"])
    captured = capsys.readouterr()
    assert result == 0
    assert "daemon:" in captured.out
    assert "threads:" in captured.out
    assert "pending notifications:" in captured.out


def test_interactive_whoami_shows_profile_items(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    repo.save(ProfileItem(type="preference", title="Style", body="I prefer concise answers."))
    repo.save(ProfileItem(type="fact", title="Work", body="I work in software."))

    monkeypatch.setattr("sys.stdin", _TextInput(":whoami\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", _mock_status)
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Core profile:" in captured.out
    assert "concise answers" in captured.out


def test_interactive_notify_lists_pending(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="n-001",
            title="Test Note",
            body="hello",
            status="pending",
            idempotency_key="k1",
        )
    )

    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Pending notifications:" in captured.out
    assert "Test Note" in captured.out


def test_interactive_notify_send_and_dismiss(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="n-002",
            title="Dismiss Me",
            body="bye",
            status="pending",
            idempotency_key="k2",
        )
    )

    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify dismiss n-002\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Dismissed: n-002" in captured.out


def test_interactive_unknown_command_shows_hints(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":th\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Did you mean:" in captured.out
    assert ":thread" in captured.out
    assert ":thread" in captured.out


def test_interactive_unknown_command_no_hints_for_unrelated(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":xyz\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Did you mean:" not in captured.out


def test_eval_command_runs_conversation_fixtures(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        [
            "--project-root",
            str(tmp_path),
            "dev",
            "eval",
            "--component",
            "conversations",
        ]
    )
    captured = capsys.readouterr()
    assert result in (0, 1)
    assert (
        "conversations:" in captured.out
        or "No conversation fixtures" in captured.out
        or "Fixtures directory not found" in captured.err
    )


def test_interactive_history_shows_recent_messages(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage

    store = ThreadStore(tmp_path)
    state = ThreadState.empty("default")
    state.messages.append(ThreadMessage(role="user", content="Hello there"))
    state.messages.append(ThreadMessage(role="assistant", content="Hi! How can I help?"))
    store.save(state)

    monkeypatch.setattr("sys.stdin", _TextInput(":history\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Recent messages in 'default':" in captured.out
    assert "> Hello there" in captured.out
    assert "< Hi! How can I help?" in captured.out


def test_interactive_archive_unarchive_delete_and_archived(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.agent.chat import ThreadState, ThreadStore

    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("alpha"))
    store.save(ThreadState.empty("beta"))

    monkeypatch.setattr(
        "sys.stdin",
        _TextInput(":archive\n:archived\n:unarchive alpha\n:archived\n:thread beta\n:delete\n:q\n"),
    )
    monkeypatch.setattr("nuself.cli.lifecycle.status", _mock_status)
    result = main(["--project-root", str(tmp_path), "thread", "open", "alpha"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Archived thread: alpha" in captured.out
    assert "alpha" in captured.out  # listed in :archived
    assert "Unarchived thread: alpha" in captured.out
    assert "No archived threads." in captured.out  # after unarchive
    assert "Deleted thread: beta" in captured.out


def test_thread_show_displays_messages(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage

    store = ThreadStore(tmp_path)
    state = ThreadState.empty("focus")
    state.messages.append(ThreadMessage(role="user", content="Tell me about memory."))
    store.save(state)

    result = main(["--project-root", str(tmp_path), "thread", "show", "focus"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Thread: focus" in captured.out
    assert "> Tell me about memory." in captured.out


def test_thread_show_missing_thread(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "thread", "show", "missing"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Thread not found: missing" in captured.err


def test_daemon_restart_stops_then_starts(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    stopped = DaemonStatus(
        running=False,
        pid=None,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    running = DaemonStatus(
        running=True,
        pid=789,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_stop(project_root: Path | None) -> DaemonStatus:
        return stopped

    def fake_start(project_root: Path | None) -> DaemonStatus:
        return running

    monkeypatch.setattr("nuself.cli.lifecycle.stop", fake_stop)
    monkeypatch.setattr("nuself.cli.lifecycle.start", fake_start)

    result = main(["--project-root", str(tmp_path), "daemon", "restart"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Stopped:" in captured.out
    assert "Started:" in captured.out
    assert "pid=789" in captured.out


def test_interactive_restart_restarts_daemon_and_keeps_session(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    stopped = DaemonStatus(
        running=False,
        pid=None,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    running = DaemonStatus(
        running=True,
        pid=789,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )
    current_status = running
    calls: list[str] = []

    def fake_status(project_root: Path | None) -> DaemonStatus:
        return current_status

    def fake_stop(project_root: Path | None) -> DaemonStatus:
        nonlocal current_status
        calls.append("stop")
        current_status = stopped
        return current_status

    def fake_start(project_root: Path | None) -> DaemonStatus:
        nonlocal current_status
        calls.append("start")
        current_status = running
        return current_status

    monkeypatch.setattr("sys.stdin", _TextInput(":r\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)
    monkeypatch.setattr("nuself.cli.lifecycle.stop", fake_stop)
    monkeypatch.setattr("nuself.cli.lifecycle.start", fake_start)

    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert calls == ["stop", "start"]
    assert "Restarted daemon:" in captured.out
    assert "pid=789" in captured.out
    assert "[daemon] session status=running thread=default" in captured.out


def test_daemon_start_with_mocked_lifecycle(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    running = DaemonStatus(
        running=True,
        pid=456,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_start(project_root: Path | None) -> DaemonStatus:
        return running

    monkeypatch.setattr("nuself.cli.lifecycle.start", fake_start)

    result = main(["--project-root", str(tmp_path), "daemon", "start"])
    captured = capsys.readouterr()
    assert result == 0
    assert "daemon running" in captured.out
    assert "pid=456" in captured.out


def test_daemon_stop_with_mocked_lifecycle(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    stopped = DaemonStatus(
        running=False,
        pid=None,
        socket_path=tmp_path / "private" / "runtime" / "nuself.sock",
        pid_path=tmp_path / "private" / "runtime" / "nuself.pid",
    )

    def fake_stop(project_root: Path | None) -> DaemonStatus:
        return stopped

    monkeypatch.setattr("nuself.cli.lifecycle.stop", fake_stop)

    result = main(["--project-root", str(tmp_path), "daemon", "stop"])
    captured = capsys.readouterr()
    assert result == 0
    assert "daemon stopped" in captured.out


def test_interactive_sources_lists_documents(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    repo.save_document(SourceDocument(id="doc-001", title="Notes", path="notes.txt", kind="text"))

    monkeypatch.setattr("sys.stdin", _TextInput(":mem sources\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "[source] [0]" in captured.out
    assert "[source]" in captured.out
    assert "Notes" in captured.out


def test_notify_clear_removes_dismissed(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="c-001", title="A", body="a", status="pending", idempotency_key="k1"))
    outbox.dismiss("c-001")

    result = main(["--project-root", str(tmp_path), "inbox", "notify", "clear"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Cleared 1 dismissed" in captured.out
    assert len(outbox.list(status="dismissed")) == 0


def test_health_command_reports_missing_config(
    tmp_path: Path, capsys: CaptureFixture
) -> None:
    result = main(["--project-root", str(tmp_path), "dev", "health"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Health issues:" in captured.out
    assert "private root missing" in captured.out


def test_interactive_search_finds_memory(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work requires long blocks."))
    repo.reindex()

    monkeypatch.setattr("sys.stdin", _TextInput(":mem search deep work\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out


def test_config_command_shows_paths(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "dev", "config"])
    captured = capsys.readouterr()
    assert result == 0
    assert "project_root:" in captured.out
    assert "private_root:" in captured.out
    assert "config_path:" in captured.out
    assert "config_file:" in captured.out
    assert "config_effective:" in captured.out
    assert "llm.0.api_key:" in captured.out


def test_memory_list_shows_entries(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work."))

    result = main(["--project-root", str(tmp_path), "memory", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "[memory] [0]" in captured.out
    assert "Focus" in captured.out


def test_memory_list_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No memory entries." in captured.out


def test_memory_list_sorts_by_importance(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    low = repo.save(MemoryEntry(type="belief", title="Low", body="Low importance.", importance=0.2))
    high = repo.save(MemoryEntry(type="belief", title="High", body="High importance.", importance=0.9))

    result = main(["--project-root", str(tmp_path), "memory", "list", "--sort-by", "importance"])
    captured = capsys.readouterr()
    assert result == 0
    high_pos = captured.out.index("High")
    low_pos = captured.out.index("Low")
    assert high_pos < low_pos
    assert low.id in captured.out
    assert high.id in captured.out


def test_memory_list_filters_by_review_state(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    draft = repo.save(MemoryEntry(type="belief", title="Draft", body="Draft entry."))
    reviewed = repo.save(MemoryEntry(type="belief", title="Reviewed", body="Reviewed entry.", review_state="reviewed"))

    result = main(["--project-root", str(tmp_path), "memory", "list", "--review-state", "reviewed"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Reviewed" in captured.out
    assert "Draft" not in captured.out
    assert reviewed.id in captured.out
    assert draft.id not in captured.out


def test_memory_show_displays_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    entry = MemoryEntry(type="belief", title="Focus", body="Deep work.")
    repo.save(entry)

    result = main(["--project-root", str(tmp_path), "memory", "show", entry.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out
    assert "Deep work." in captured.out


def test_memory_show_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "show", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Memory entry not found: missing-id" in captured.err


def test_memory_search_finds_match(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work."))
    repo.save(MemoryEntry(type="belief", title="Relax", body="Take breaks."))

    result = main(["--project-root", str(tmp_path), "memory", "search", "deep"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out
    assert "Relax" not in captured.out


def test_memory_search_no_match_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "search", "xyz"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No matching memory entries." in captured.out


def test_memory_source_list_shows_documents(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    repo.save_document(SourceDocument(id="src-001", path="/tmp/test.txt", title="Test Source", kind="text"))

    result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "[source] [0]" in captured.out
    assert "Test Source" in captured.out


def test_memory_source_list_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No source documents." in captured.out


def test_memory_source_show_displays_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    doc = SourceDocument(id="src-002", path="/tmp/test.txt", title="Test Source", kind="text")
    repo.save_document(doc)

    result = main(["--project-root", str(tmp_path), "memory", "source", "show", doc.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Test Source" in captured.out


def test_memory_source_show_missing_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "source", "show", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Source document not found: missing-id" in captured.err


def test_memory_source_delete_removes_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    doc = SourceDocument(id="src-003", path="/tmp/test.txt", title="Test Source", kind="text")
    repo.save_document(doc)

    result = main(["--project-root", str(tmp_path), "memory", "source", "delete", doc.id])
    assert result == 0
    assert len(repo.list_documents()) == 0


def test_memory_source_chunks_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "source", "chunks", "some-id"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No source chunks." in captured.out


def test_memory_source_search_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "source", "search", "xyz"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No matching source chunks." in captured.out


def test_memory_source_extract_missing_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "source", "extract", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Source document not found: missing-id" in captured.err


def test_memory_stats_shows_empty_state(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "stats"])
    captured = capsys.readouterr()
    assert result == 0
    assert "entries_total: 0" in captured.out


def test_memory_unquarantine_restores_draft(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.domain.memory import MemoryEntryType
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(MemoryEntry(type=cast(MemoryEntryType, "truly_unknown_type"), title="Quarantined", body="Body"))
    assert entry.review_state == "quarantined"

    result = main(["--project-root", str(tmp_path), "memory", "unquarantine", entry.id])
    captured = capsys.readouterr()
    assert result == 0
    assert f"Unquarantined memory entry: {entry.id}" in captured.out
    assert repo.get(entry.id).review_state == "draft"


def test_memory_profile_list_shows_items(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    repo.save(ProfileItem(type="preference", title="Style", body="Concise."))

    result = main(["--project-root", str(tmp_path), "memory", "profile", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "[profile] [0]" in captured.out
    assert "Style" in captured.out


def test_memory_profile_list_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "profile", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No profile items." in captured.out


def test_memory_profile_list_sorts_by_importance(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    low = repo.save(ProfileItem(type="preference", title="Low", body="Low importance.", importance=0.2))
    high = repo.save(ProfileItem(type="preference", title="High", body="High importance.", importance=0.9))

    result = main(["--project-root", str(tmp_path), "memory", "profile", "list", "--sort-by", "importance"])
    captured = capsys.readouterr()
    assert result == 0
    high_pos = captured.out.index("High")
    low_pos = captured.out.index("Low")
    assert high_pos < low_pos
    assert low.id in captured.out
    assert high.id in captured.out


def test_memory_profile_show_displays_item(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    item = ProfileItem(type="preference", title="Style", body="Concise.")
    repo.save(item)

    result = main(["--project-root", str(tmp_path), "memory", "profile", "show", item.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Style" in captured.out
    assert "Concise." in captured.out


def test_memory_profile_show_missing_item(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "profile", "show", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Profile item not found: missing-id" in captured.err


def test_memory_profile_search_finds_match(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    repo.save(ProfileItem(type="preference", title="Style", body="Concise."))
    repo.save(ProfileItem(type="fact", title="Work", body="Software."))

    result = main(["--project-root", str(tmp_path), "memory", "profile", "search", "concise"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Style" in captured.out
    assert "Work" not in captured.out


def test_memory_profile_delete_removes_item(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.profile.repository import ProfileItemRepository
    from nuself.domain.profile import ProfileItem

    repo = ProfileItemRepository(tmp_path)
    item = ProfileItem(type="preference", title="Style", body="Concise.")
    repo.save(item)

    result = main(["--project-root", str(tmp_path), "memory", "profile", "delete", item.id])
    assert result == 0
    assert len(repo.list()) == 0


def test_memory_profile_reindex_rebuilds_index(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "profile", "reindex"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Rebuilt profile index:" in captured.out


def test_memory_relations_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "relations"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No memory relations." in captured.out


def test_memory_graph_nodes_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "graph", "nodes"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No symbolic graph nodes." in captured.out


def test_memory_graph_edges_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "graph", "edges"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No symbolic graph edges." in captured.out


def test_memory_graph_search_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "graph", "search", "test"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No symbolic graph matches." in captured.out


def test_memory_graph_path_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        ["--project-root", str(tmp_path), "memory", "graph", "path", "a", "b"]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "No path found." in captured.out


def test_memory_graph_closure_missing_relation(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        ["--project-root", str(tmp_path), "memory", "graph", "closure", "a"]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert "--relation is required" in captured.out


def test_memory_candidate_list_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "review", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No memory candidates." in captured.out


def test_memory_candidate_list_filters_by_review_state(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    pending = repo.save(MemoryCandidate(type="belief", title="Pending", body="Pending candidate."))
    accepted = repo.save(MemoryCandidate(type="belief", title="Accepted", body="Accepted candidate.", review_state="accepted"))

    result = main(["--project-root", str(tmp_path), "memory", "review", "list", "--review-state", "accepted", "--all"])
    captured = capsys.readouterr()
    assert result == 0
    assert "[candidate] [0]" in captured.out
    assert "Accepted" in captured.out
    assert "Pending" not in captured.out
    assert accepted.id in captured.out
    assert pending.id not in captured.out


def test_memory_candidate_list_sorts_by_importance(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    low = repo.save(MemoryCandidate(type="belief", title="Low", body="Low importance.", importance=0.2))
    high = repo.save(MemoryCandidate(type="belief", title="High", body="High importance.", importance=0.9))

    result = main(["--project-root", str(tmp_path), "memory", "review", "list", "--sort-by", "importance"])
    captured = capsys.readouterr()
    assert result == 0
    high_pos = captured.out.index("High")
    low_pos = captured.out.index("Low")
    assert high_pos < low_pos
    assert low.id in captured.out
    assert high.id in captured.out


def test_memory_candidate_show_displays_candidate(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    candidate = MemoryCandidate(action="create", type="belief", title="Focus", body="Deep work.")
    repo.save(candidate)

    result = main(["--project-root", str(tmp_path), "memory", "review", "show", candidate.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out
    assert "Deep work." in captured.out


def test_memory_candidate_show_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "review", "show", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Memory candidate not found: missing-id" in captured.err


def test_memory_candidate_accept_creates_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    candidate = MemoryCandidate(action="create", type="belief", title="Focus", body="Deep work.")
    repo.save(candidate)

    result = main(
        ["--project-root", str(tmp_path), "memory", "review", "accept", candidate.id]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Accepted memory candidate:" in captured.out


def test_memory_candidate_reject_pending(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    candidate = MemoryCandidate(action="create", type="belief", title="Focus", body="Deep work.")
    repo.save(candidate)

    result = main(
        ["--project-root", str(tmp_path), "memory", "review", "reject", candidate.id]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Rejected memory candidate:" in captured.out


def test_memory_candidate_edit_updates_fields(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    candidate = MemoryCandidate(action="create", type="belief", title="Focus", body="Deep work.")
    repo.save(candidate)

    result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "review",
            "edit",
            candidate.id,
            "--title",
            "Concentration",
            "--body",
            "Focus deeply.",
        ]
    )
    assert result == 0
    updated = repo.get(candidate.id)
    assert updated.title == "Concentration"
    assert updated.body == "Focus deeply."


def test_memory_candidate_merge_updates_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
    from nuself.domain.memory import MemoryCandidate, MemoryEntry

    entry_repo = MemoryEntryRepository(tmp_path)
    entry = MemoryEntry(type="belief", title="Focus", body="Deep work.")
    entry_repo.save(entry)

    cand_repo = MemoryCandidateRepository(tmp_path)
    candidate = MemoryCandidate(
        action="update", type="belief", title="Focus", body="Focus deeply.", target_entry_id=entry.id
    )
    cand_repo.save(candidate)

    result = main(
        ["--project-root", str(tmp_path), "memory", "review", "merge", candidate.id, entry.id]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Merged memory candidate:" in captured.out


def test_memory_add_creates_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository

    result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--title",
            "Focus",
            "--body",
            "Deep work is important.",
            "--type",
            "belief",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out
    assert len(MemoryEntryRepository(tmp_path).list()) == 1


def test_memory_delete_removes_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    entry = MemoryEntry(type="belief", title="Focus", body="Deep work.")
    repo.save(entry)

    result = main(["--project-root", str(tmp_path), "memory", "delete", entry.id])
    assert result == 0
    assert len(repo.list()) == 0


def test_memory_delete_accepts_batch_index_selection(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    for i in range(4):
        repo.save(MemoryEntry(type="belief", title=f"Entry {i}", body=f"Body {i}."))
    listed = repo.list()
    deleted_ids = {listed[0].id, listed[2].id, listed[3].id}
    remaining_id = listed[1].id

    result = main(["--project-root", str(tmp_path), "memory", "delete", "0,2-3"])
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("Deleted memory entry:") == 3
    assert {entry.id for entry in repo.list()} == {remaining_id}
    assert deleted_ids.isdisjoint({entry.id for entry in repo.list()})


def test_memory_edit_updates_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    entry = MemoryEntry(type="belief", title="Focus", body="Deep work.")
    repo.save(entry)

    result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "edit",
            entry.id,
            "--title",
            "Concentration",
            "--body",
            "Focus deeply.",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Concentration" in captured.out
    updated = repo.get(entry.id)
    assert updated.title == "Concentration"
    assert updated.body == "Focus deeply."


def test_memory_reindex_rebuilds_indexes(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "reindex"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Rebuilt memory index:" in captured.out
    assert "Rebuilt relation index:" in captured.out
    assert "Rebuilt symbolic graph:" in captured.out
    assert "Rebuilt source index:" in captured.out


def test_memory_types_lists_registered_types(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "types"])
    captured = capsys.readouterr()
    assert result == 0
    assert "belief: a claim or stance" in captured.out
    assert "episode: a concise event summary" in captured.out
    assert "persona_instruction: persona instruction memory" in captured.out


def test_memory_types_json_output(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "types", "--json"])
    captured = capsys.readouterr()
    assert result == 0
    assert '"type": "belief"' in captured.out
    assert '"description":' in captured.out
    assert '"example":' in captured.out


def test_daemon_list_shows_status(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "pid" in captured.out


def test_daemon_logs_shows_empty(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "logs"])
    assert result == 0


def test_memory_export_writes_json(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work."))
    output = tmp_path / "export.json"

    result = main(["--project-root", str(tmp_path), "memory", "export", "-o", str(output)])
    captured = capsys.readouterr()
    assert result == 0
    assert "Exported 1 memory entries" in captured.out
    assert output.exists()
    import json

    data = cast(list[object], json.loads(output.read_text(encoding="utf-8")))
    assert len(data) == 1
    assert cast(dict[str, object], data[0])["title"] == "Focus"


def test_memory_import_reads_json(tmp_path: Path, capsys: CaptureFixture) -> None:
    import json

    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    # Export first
    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work."))
    export_path = tmp_path / "export.json"
    entries = repo.list()
    data = [entry.to_wire() for entry in entries]
    export_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Clear and import
    for entry in MemoryEntryRepository(tmp_path).list():
        repo.delete(entry.id)
    repo.reindex()
    assert len(MemoryEntryRepository(tmp_path).list()) == 0

    result = main(["--project-root", str(tmp_path), "memory", "import", str(export_path)])
    captured = capsys.readouterr()
    assert result == 0
    assert "Imported 1 memory entries" in captured.out
    assert len(MemoryEntryRepository(tmp_path).list()) == 1




@pytest.mark.parametrize(
    "argv",
    [
        ["daemon", "--help"],
        ["chat", "--help"],
        ["attach", "--help"],
        ["memory", "--help"],
        ["thread", "--help"],
        ["inbox", "--help"],
        ["reason", "--help"],
        ["trace", "--help"],
        ["persona", "--help"],
        ["dev", "--help"],
    ],
)
def test_top_level_subcommand_help(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 0


def test_top_level_help_describes_commands(capsys: CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    captured = capsys.readouterr()

    assert exc_info.value.code == 0
    assert "memory" in captured.out
    assert "Manage memory entries, sources, profiles, reviews, and" in captured.out
    assert "the memory graph." in captured.out
    assert "reason" in captured.out
    assert "Manage long-run reasoning threads." in captured.out
    assert "dev" in captured.out
    assert "Run diagnostics, logs, config inspection, and evals." in captured.out


def test_reason_cli_start_list_show_and_advance(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("nuself.reason.service.generate_reasoning_prompt", _test_reason_prompt_generator)

    start_result = main(["--project-root", str(tmp_path), "reason", "start", "How should I keep thinking?"])
    start_output = capsys.readouterr().out
    assert start_result == 0
    assert "Started reasoning thread:" in start_output

    list_result = main(["--project-root", str(tmp_path), "reason", "list"])
    list_output = capsys.readouterr().out
    assert list_result == 0
    assert "[0] [reason] status=[active] priority=normal" in list_output
    assert "How should I keep thinking?" in list_output

    show_result = main(["--project-root", str(tmp_path), "reason", "show", "0"])
    show_output = capsys.readouterr().out
    assert show_result == 0
    assert "[reason] How should I keep thinking?" in show_output

    advance_result = main(["--project-root", str(tmp_path), "reason", "advance", "0"])
    advance_output = capsys.readouterr()
    assert advance_result == 1
    assert "Error:" in advance_output.err or "Error:" in advance_output.out


def test_reflection_cli_promote_creates_reason_and_trace(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("nuself.reason.service.generate_reasoning_prompt", _test_reason_prompt_generator)

    entry = ReflectionEntry(
        id="reflection-cli",
        title="Follow a long idea",
        body="This idea should move into reason.",
        candidate_type="question",
        confidence=0.8,
        novelty=0.7,
        urgency=0.4,
        interruption_cost=0.2,
        composite_score=0.6,
        status="pending",
        discussion_approved=True,
        discussion_trace=(),
        deep_link="nuself://thread/reflections",
        created_at="2026-05-19T00:00:00+00:00",
        reviewed_at=None,
    )
    ReflectionRepository(tmp_path).add(entry)

    result = main(["--project-root", str(tmp_path), "inbox", "reflection", "promote", entry.id])
    output = capsys.readouterr().out

    assert result == 0
    assert "Promoted reflection to reason thread:" in output
    assert "Follow a long idea" in output
    assert len(TraceQueryService(tmp_path).list_traces(kind="promotion")) == 1


def test_interactive_reason_without_args_shows_help(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    def fake_status(project_root: Path | None) -> DaemonStatus:
        return _mock_status(tmp_path)

    monkeypatch.setattr("sys.stdin", _TextInput(":reason\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)

    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Reason commands:" in captured.out
    assert "No reason threads." not in captured.out


def test_interactive_reason_list_shows_threads(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    def fake_status(project_root: Path | None) -> DaemonStatus:
        return _mock_status(tmp_path)

    ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator).start_thread("Track this reasoning thread")
    monkeypatch.setattr("sys.stdin", _TextInput(":reason list\n:q\n"))
    monkeypatch.setattr("nuself.cli.lifecycle.status", fake_status)

    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[0] [reason] status=[active] priority=normal" in captured.out
    assert "Track this reasoning thread" in captured.out


def _test_reason_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."



@pytest.mark.parametrize(
    "argv",
    [
        ["daemon", "start", "--help"],
        ["daemon", "stop", "--help"],
        ["daemon", "restart", "--help"],
        ["daemon", "status", "--help"],
        ["daemon", "list", "--help"],
        ["daemon", "logs", "--help"],
        ["daemon", "attach", "--help"],
        ["inbox", "reflection", "--help"],
        ["inbox", "reflection", "list", "--help"],
        ["inbox", "reflection", "show", "--help"],
        ["inbox", "reflection", "dismiss", "--help"],
        ["inbox", "reflection", "archive", "--help"],
        ["inbox", "reflection", "promote", "--help"],
        ["inbox", "reflection", "organize", "--help"],
        ["inbox", "notify", "--help"],
        ["inbox", "notify", "list", "--help"],
        ["inbox", "notify", "show", "--help"],
        ["inbox", "notify", "send", "--help"],
        ["inbox", "notify", "dismiss", "--help"],
        ["inbox", "notify", "clear", "--help"],
        ["dev", "status", "--help"],
        ["dev", "health", "--help"],
        ["dev", "config", "--help"],
        ["dev", "logs", "--help"],
        ["dev", "eval", "--help"],
        ["memory", "list", "--help"],
        ["memory", "preview", "--help"],
        ["memory", "show", "--help"],
        ["memory", "add", "--help"],
        ["memory", "edit", "--help"],
        ["memory", "delete", "--help"],
        ["memory", "search", "--help"],
        ["memory", "stats", "--help"],
        ["memory", "relations", "--help"],
        ["memory", "graph", "--help"],
        ["memory", "update", "--help"],
        ["memory", "optimize", "--help"],
        ["memory", "export", "--help"],
        ["memory", "import", "--help"],
        ["memory", "profile", "--help"],
        ["memory", "review", "--help"],
        ["memory", "types", "--help"],
        ["memory", "source", "--help"],
        ["memory", "reindex", "--help"],
        ["thread", "list", "--help"],
        ["thread", "show", "--help"],
        ["thread", "new", "--help"],
        ["thread", "open", "--help"],
        ["thread", "rename", "--help"],
        ["thread", "branch", "--help"],
        ["thread", "archive", "--help"],
        ["thread", "delete", "--help"],
        ["thread", "unarchive", "--help"],
        ["thread", "archived", "--help"],
        ["persona", "list", "--help"],
        ["persona", "show", "--help"],
        ["persona", "delete", "--help"],
    ],
)
def test_nested_subcommand_help(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["source", "--help"],
        ["reflection", "--help"],
        ["notify", "--help"],
        ["logs", "--help"],
        ["status", "--help"],
        ["health", "--help"],
        ["config", "--help"],
        ["eval", "--help"],
        ["open", "--help"],
        ["memory", "candidate", "--help"],
        ["thread", "create", "--help"],
    ],
)
def test_removed_v02_command_paths_fail(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 2


def test_help_does_not_emit_langgraph_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nuself.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage: nuself" in result.stdout
    assert "LangChainPendingDeprecationWarning" not in result.stderr


def test_cli_version_matches_project_metadata(capsys: CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    captured = capsys.readouterr()
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = cast(dict[str, object], pyproject["project"])

    assert exc_info.value.code == 0
    assert captured.out == f"nuself {project['version']}\n"
    assert captured.err == ""



@pytest.mark.parametrize(
    "argv",
    [
        ["memory", "graph", "nodes", "--help"],
        ["memory", "graph", "edges", "--help"],
        ["memory", "graph", "search", "--help"],
        ["memory", "graph", "path", "--help"],
        ["memory", "graph", "closure", "--help"],
        ["memory", "profile", "list", "--help"],
        ["memory", "profile", "search", "--help"],
        ["memory", "profile", "show", "--help"],
        ["memory", "profile", "delete", "--help"],
        ["memory", "profile", "reindex", "--help"],
        ["memory", "review", "list", "--help"],
        ["memory", "review", "show", "--help"],
        ["memory", "review", "accept", "--help"],
        ["memory", "review", "reject", "--help"],
        ["memory", "review", "edit", "--help"],
        ["memory", "review", "merge", "--help"],
        ["memory", "source", "ingest", "--help"],
        ["memory", "source", "list", "--help"],
        ["memory", "source", "show", "--help"],
        ["memory", "source", "delete", "--help"],
        ["memory", "source", "chunks", "--help"],
        ["memory", "source", "search", "--help"],
        ["memory", "source", "extract", "--help"],
    ],
)
def test_third_level_subcommand_help(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 0


def test_notify_watch_detects_new_entries(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B", status="pending", idempotency_key="k1"))

    sleep_calls: list[int] = []

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(int(seconds))
        # Inject after first poll; exit after second poll prints it
        if len(sleep_calls) == 1:
            outbox.add(
                OutboxEntry(id="e2", title="Second", body="B", status="pending", idempotency_key="k2")
            )
        if len(sleep_calls) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", _fake_sleep)
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "watch", "--interval", "1"])
    output = capsys.readouterr().out

    assert result == 0
    assert "Watching outbox every 1s" in output
    assert "Second" in output
    assert "Stopped watching" in output


def test_notify_watch_default_interval(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    sleep_calls: list[int] = []

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(int(seconds))
        raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", _fake_sleep)
    result = main(["--project-root", str(tmp_path), "inbox", "notify", "watch"])
    output = capsys.readouterr().out

    assert result == 0
    assert sleep_calls == [5]
    assert "Watching outbox every 5s" in output


def test_repl_watch_detects_new_entries(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B", status="pending", idempotency_key="k1"))

    sleep_calls: list[int] = []

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(int(seconds))
        if len(sleep_calls) == 1:
            outbox.add(
                OutboxEntry(id="e2", title="Second", body="B", status="pending", idempotency_key="k2")
            )
        if len(sleep_calls) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", _fake_sleep)
    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify watch\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Watching outbox" in captured.out
    assert "Second" in captured.out
    assert "Stopped watching" in captured.out
    assert sleep_calls == [2, 2]


def test_repl_notify_watch_subcommand(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B", status="pending", idempotency_key="k1"))

    sleep_calls: list[int] = []

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(int(seconds))
        if len(sleep_calls) == 1:
            outbox.add(
                OutboxEntry(id="e2", title="Second", body="B", status="pending", idempotency_key="k2")
            )
        if len(sleep_calls) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", _fake_sleep)
    monkeypatch.setattr("sys.stdin", _TextInput(":inbox notify watch\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Watching outbox" in captured.out
    assert "Second" in captured.out
    assert "Stopped watching" in captured.out


def test_trace_cli_lists_shows_and_searches_records(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.trace import ThoughtTrace, TraceRepository

    trace = TraceRepository(tmp_path).save_trace(
        ThoughtTrace(
            kind="chat_turn",
            title="Temporal memory answer",
            summary="NuSelf answered with observed_at context.",
            inputs=["thread:default:1:user"],
            outputs=["thread:default:2:assistant"],
            evidence_refs=["mem_123"],
            thread_id="default",
        )
    )

    list_result = main(["--project-root", str(tmp_path), "trace", "list"])
    list_output = capsys.readouterr().out
    show_result = main(["--project-root", str(tmp_path), "trace", "show", "0"])
    show_output = capsys.readouterr().out
    search_result = main(["--project-root", str(tmp_path), "trace", "search", "observed_at"])
    search_output = capsys.readouterr().out

    assert list_result == 0
    assert show_result == 0
    assert search_result == 0
    assert "Temporal memory answer" in list_output
    assert "kind=chat_turn" in list_output
    assert trace.id in show_output
    assert "mem_123" in show_output
    assert "Temporal memory answer" in search_output


def test_trace_cli_hides_internal_records_by_default(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.trace import ThoughtTrace, TraceRepository

    repo = TraceRepository(tmp_path)
    repo.save_trace(ThoughtTrace(kind="decision", title="Visible trace", summary="Visible."))
    repo.save_trace(
        ThoughtTrace(kind="decision", title="Internal trace", summary="Hidden.", visibility="internal")
    )

    main(["--project-root", str(tmp_path), "trace", "list"])
    default_output = capsys.readouterr().out
    main(["--project-root", str(tmp_path), "trace", "list", "--visibility", "all"])
    all_output = capsys.readouterr().out

    assert "Visible trace" in default_output
    assert "Internal trace" not in default_output
    assert "Internal trace" in all_output


def test_repl_trace_lists_records(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    from nuself.trace import ThoughtTrace, TraceRepository

    TraceRepository(tmp_path).save_trace(
        ThoughtTrace(kind="decision", title="REPL trace", summary="Shown from interactive trace command.")
    )

    monkeypatch.setattr("sys.stdin", _TextInput(":trace\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()

    assert result == 0
    assert "REPL trace" in captured.out
