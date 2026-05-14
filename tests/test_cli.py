from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Protocol, cast

import pytest

from nuself import cli
from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.cli import build_parser, main
from nuself.daemon.client import DaemonConnectionError
from nuself.daemon.protocol import DaemonResponse
from nuself.daemon.lifecycle import DaemonStatus
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence


def _mock_status(project_root: Path) -> DaemonStatus:
    return DaemonStatus(
        running=True, pid=123, socket_path=Path("/dev/null"), pid_path=Path("/dev/null")
    )
from nuself.domain.profile import ProfileItem
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.logs import read_log_events, write_log_event


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
    if cli.readline is not None:
        history_path = tmp_path / "private" / "runtime" / "interactive_history"
        assert history_path.is_file()
        assert "hello" in history_path.read_text(encoding="utf-8")


def test_unknown_interactive_command_shows_help_and_keeps_session_open(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":bad\nhello\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Unknown interactive command: :bad" in captured.out
    assert "Interactive commands:" in captured.out
    assert ":memory preview memory entries" in captured.out
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
    monkeypatch.setattr("sys.stdin", _TextInput(":memory\n:q\n"))

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
    assert "[mem] reviewed belief" in captured.out
    assert "Readable memory" in captured.out
    assert "#display" in captured.out
    assert "Terminal memory output should be easy to scan." not in captured.out


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
    assert "[mem] Readable detail" in captured.out
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
    main(["--project-root", str(tmp_path), "source", "ingest", str(source_path)])
    capsys.readouterr()
    monkeypatch.setattr(
        "sys.stdin",
        _TextInput(":mem candidates\n:mem profile readable\n:mem sources\n:q\n"),
    )

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[cand] pending" in captured.out
    assert "Candidate display" in captured.out
    assert "[profile] profile_fact" in captured.out
    assert "Profile display" in captured.out
    assert "[src]" in captured.out
    assert "Source Display" in captured.out


def test_interactive_status_command_shows_daemon_status(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":status\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "daemon stopped" in captured.out


def test_interactive_logs_command_shows_recent_activity(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    write_log_event("chat", "turn_completed", "chat turn completed", project_root=tmp_path)
    monkeypatch.setattr("sys.stdin", _TextInput(":logs\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[chat] chat turn completed" in captured.out


def test_interactive_turn_prints_activity_events(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("hello\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[chat] one-shot chat turn completed" in captured.out


def test_interactive_export_saves_connection_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("first message\n:export\nsecond message\n:export\n:q\n"))

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


def test_interactive_export_copy_copies_saved_transcript(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    copied: list[str] = []

    def fake_copy(text: str) -> tuple[bool, str]:
        copied.append(text)
        return True, ""

    monkeypatch.setattr("sys.stdin", _TextInput("share this\n:export --copy\n:q\n"))
    monkeypatch.setattr("nuself.cli._copy_text_to_clipboard", fake_copy)

    result = main(["--project-root", str(tmp_path), "chat"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Saved transcript:" in captured.out
    assert "Copied transcript to clipboard." in captured.out
    assert len(copied) == 1
    assert "share this" in copied[0]
    assert "# NuSelf Chat Transcript" in copied[0]


def test_interactive_history_skips_consecutive_duplicates(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput("same\nsame\n:q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    capsys.readouterr()

    assert result == 0
    if cli.readline is not None:
        history_path = tmp_path / "private" / "runtime" / "interactive_history"
        history_lines = history_path.read_text(encoding="utf-8").splitlines()
        assert history_lines.count("same") == 1


def test_interactive_history_dedupes_existing_consecutive_duplicates(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    history_path = tmp_path / "private" / "runtime" / "interactive_history"
    history_path.parent.mkdir(parents=True)
    history_path.write_text("old\nold\nnew\n:q\n", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))

    result = main(["--project-root", str(tmp_path), "chat"])
    capsys.readouterr()

    assert result == 0
    if cli.readline is not None:
        history = [
            cli.readline.get_history_item(index)
            for index in range(1, cli.readline.get_current_history_length() + 1)
        ]
        assert history == ["old", "new", ":q"]


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

    result = main(["--project-root", str(tmp_path), "logs", "--component", "chat", "--tail", "5", "--no-color"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[chat] chat turn completed" in captured.out
    assert "thread=default" in captured.out
    assert "[memory]" not in captured.out


def test_logs_command_can_render_json(tmp_path: Path, capsys: CaptureFixture) -> None:
    write_log_event("daemon", "started", "daemon started", project_root=tmp_path)

    result = main(["--project-root", str(tmp_path), "logs", "--component", "daemon", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"component": "daemon"' in captured.out
    assert '"event": "started"' in captured.out


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
    assert "preview" in captured.out
    assert "reindex" in captured.out


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
    entry_id = add_output.split()[3]

    list_result = main(["--project-root", str(tmp_path), "memory", "list"])
    list_output = capsys.readouterr().out

    show_result = main(["--project-root", str(tmp_path), "memory", "show", entry_id])
    show_output = capsys.readouterr().out

    delete_result = main(["--project-root", str(tmp_path), "memory", "delete", entry_id])
    delete_output = capsys.readouterr().out

    assert add_result == 0
    assert list_result == 0
    assert show_result == 0
    assert delete_result == 0
    assert "Clarity" in list_output
    assert "State assumptions explicitly." in show_output
    assert f"Deleted memory entry: {entry_id}" in delete_output


def test_memory_add_infers_type_without_manual_type(tmp_path: Path, capsys: CaptureFixture) -> None:
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
    entry_id = add_output.split()[3]

    entry = MemoryEntryRepository(tmp_path).get(entry_id)

    assert add_result == 0
    assert entry.type == "preference"
    assert entry.title.startswith("I prefer terse CLI summaries")
    assert entry.title.endswith("...")
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

    list_result = main(["--project-root", str(tmp_path), "memory", "candidate", "list"])
    list_output = capsys.readouterr().out
    show_result = main(["--project-root", str(tmp_path), "memory", "candidate", "show", candidate.id])
    show_output = capsys.readouterr().out
    accept_result = main(["--project-root", str(tmp_path), "memory", "candidate", "accept", candidate.id])
    accept_output = capsys.readouterr().out

    entries = MemoryEntryRepository(tmp_path).list()

    assert list_result == 0
    assert show_result == 0
    assert accept_result == 0
    assert "Temporal memory" in list_output
    assert f"id={candidate.id}" in show_output
    assert "thread:thread:default:4-6" in show_output
    assert "Accepted memory candidate:" in accept_output
    assert entries[0].observed_at == "2026-05-07"
    assert entries[0].evidence[0].source_ref == "thread:default:4-6"
    assert entries[0].temporal_note == "The user asked for visible thought evolution."


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
            "candidate",
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
        ["--project-root", str(tmp_path), "memory", "candidate", "merge", merge_candidate.id, entry.id]
    )
    merge_output = capsys.readouterr().out
    reject_result = main(
        ["--project-root", str(tmp_path), "memory", "candidate", "reject", reject_candidate.id]
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
    list_result = main(["--project-root", str(tmp_path), "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[1]
    show_result = main(["--project-root", str(tmp_path), "source", "show", source_id])
    show_output = capsys.readouterr().out
    chunks_result = main(["--project-root", str(tmp_path), "source", "chunks", source_id])
    chunks_output = capsys.readouterr().out

    assert ingest_result == 0
    assert list_result == 0
    assert show_result == 0
    assert chunks_result == 0
    assert "Source ingest: documents=1 chunks=1" in ingest_output
    assert "Source Essay" in list_output
    assert "#mirror" in list_output
    assert "shareable" in list_output
    assert "origin: notebook" in show_output
    assert "source_date: 2026-05-07" in show_output
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
    main(["--project-root", str(tmp_path), "source", "ingest", str(source_path)])
    capsys.readouterr()

    search_result = main(
        ["--project-root", str(tmp_path), "source", "search", "durable citation", "--limit", "3"]
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
    main(["--project-root", str(tmp_path), "source", "ingest", str(source_path)])
    capsys.readouterr()

    list_result = main(["--project-root", str(tmp_path), "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[1]

    extract_result = main(["--project-root", str(tmp_path), "source", "extract", source_id])
    extract_output = capsys.readouterr().out
    candidate_list_result = main(["--project-root", str(tmp_path), "memory", "candidate", "list"])
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
    main(["--project-root", str(tmp_path), "source", "ingest", str(source_path)])
    capsys.readouterr()
    list_result = main(["--project-root", str(tmp_path), "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[1]
    main(["--project-root", str(tmp_path), "source", "extract", source_id])
    capsys.readouterr()

    delete_result = main(["--project-root", str(tmp_path), "source", "delete", source_id])
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
    main(["--project-root", str(tmp_path), "source", "ingest", str(source_path)])
    capsys.readouterr()
    list_result = main(["--project-root", str(tmp_path), "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split()[1]
    main(["--project-root", str(tmp_path), "source", "extract", source_id])
    capsys.readouterr()
    candidate_repo = MemoryCandidateRepository(tmp_path)
    candidate_id = candidate_repo.list()[0].id
    main(["--project-root", str(tmp_path), "memory", "candidate", "accept", candidate_id])
    capsys.readouterr()
    profile_repo = ProfileItemRepository(tmp_path)
    profile_id = profile_repo.list()[0].id

    delete_result = main(["--project-root", str(tmp_path), "memory", "profile", "delete", profile_id])
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
    result = main(["--project-root", str(tmp_path), "thread", "create", "new-thread"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Created thread: new-thread" in captured.out
    assert "new-thread.json" in [p.name for p in (tmp_path / "private" / "threads").glob("*.json")]


def test_thread_create_fails_when_thread_exists(tmp_path: Path, capsys: CaptureFixture) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("existing"))

    result = main(["--project-root", str(tmp_path), "thread", "create", "existing"])
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

    result = main(["--project-root", str(tmp_path), "open", "focus"])
    captured = capsys.readouterr()

    assert result == 0
    assert "thread=focus" in captured.out


def test_open_missing_thread_fails(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "open", "missing"])
    captured = capsys.readouterr()

    assert result == 1
    assert "Thread not found: missing" in captured.err


def test_open_create_makes_thread_and_enters_repl(
    tmp_path: Path, capsys: CaptureFixture, monkeypatch: MonkeyPatchFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _TextInput(":q\n"))

    result = main(["--project-root", str(tmp_path), "open", "new-thread", "--create"])
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

    result = main(["--project-root", str(tmp_path), "open", "focus", "--message", "hello"])
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

    list_result = main(["--project-root", str(tmp_path), "notify", "list"])
    list_output = capsys.readouterr().out

    show_result = main(["--project-root", str(tmp_path), "notify", "show", entry.id])
    show_output = capsys.readouterr().out

    send_result = main(["--project-root", str(tmp_path), "notify", "send", entry.id])
    send_output = capsys.readouterr().out

    dismiss_result = main(["--project-root", str(tmp_path), "notify", "dismiss", entry.id])
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
    result = main(["--project-root", str(tmp_path), "notify", "show", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_send_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "notify", "send", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_dismiss_missing_entry(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "notify", "dismiss", "missing-id"])
    output = capsys.readouterr().err
    assert result == 1
    assert "not found" in output


def test_notify_show_by_index(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Second", body="B2", status="pending", idempotency_key="k2"))

    result = main(["--project-root", str(tmp_path), "notify", "show", "-i", "1"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Second" in output


def test_notify_dismiss_by_index(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Second", body="B2", status="pending", idempotency_key="k2"))

    result = main(["--project-root", str(tmp_path), "notify", "dismiss", "--by-index", "0"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Dismissed: e1" in output


def test_notify_by_index_out_of_range(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="First", body="B1", status="pending", idempotency_key="k1"))

    result = main(["--project-root", str(tmp_path), "notify", "show", "-i", "5"])
    output = capsys.readouterr().err
    assert result == 1
    assert "Invalid index" in output


def test_notify_list_empty(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "notify", "list"])
    output = capsys.readouterr().out
    assert result == 0
    assert "No outbox entries." in output


def test_notify_list_filters_by_status(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="Pending", body="B", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="Sent", body="B", status="sent", idempotency_key="k2"))
    outbox.add(OutboxEntry(id="e3", title="Failed", body="B", status="failed", idempotency_key="k3"))

    result = main(["--project-root", str(tmp_path), "notify", "list", "--status", "pending"])
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
    result = main(["--project-root", str(tmp_path), "notify", "show", "e1"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Test Title" in output
    assert "Test Body" in output
    assert "pending" in output
    assert "nuself://thread/default" in output
    assert "idempotency:  k1" in output


def test_notify_stats_counts(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="A", body="B", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="A", body="B", status="sent", idempotency_key="k2"))
    outbox.add(OutboxEntry(id="e3", title="A", body="B", status="sent", idempotency_key="k3"))
    outbox.add(OutboxEntry(id="e4", title="A", body="B", status="failed", idempotency_key="k4"))

    result = main(["--project-root", str(tmp_path), "notify", "stats"])
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

    monkeypatch.setattr("sys.stdin", _TextInput(":notify list\n:q\n"))
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

    monkeypatch.setattr("sys.stdin", _TextInput(":notify show e1\n:q\n"))
    result = main(["--project-root", str(tmp_path), "chat"])
    output = capsys.readouterr().out
    assert result == 0
    assert "Test" in output
    assert "Body" in output


def test_open_with_deep_link_parses_thread_id(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(
        ["--project-root", str(tmp_path), "open", "--deep-link", "nuself://thread/my-thread"]
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
        ["--project-root", str(tmp_path), "open", "--deep-link", "https://example.com"]
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
            "open",
            "--deep-link",
            "nuself://new-thread?title=proactive-thread&message=hello%20there",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert "Created thread: proactive-thread" in captured.out


def test_status_command_shows_daemon_threads_and_notifications(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "status"])
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

    monkeypatch.setattr("sys.stdin", _TextInput(":notify\n:q\n"))
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

    monkeypatch.setattr("sys.stdin", _TextInput(":notify dismiss n-002\n:q\n"))
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
    assert ":threads" in captured.out


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
    result = main(["--project-root", str(tmp_path), "open", "alpha"])
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

    monkeypatch.setattr("sys.stdin", _TextInput(":sources\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Imported sources:" in captured.out
    assert "Notes" in captured.out


def test_notify_clear_removes_dismissed(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.notification import NotificationOutbox, OutboxEntry

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="c-001", title="A", body="a", status="pending", idempotency_key="k1"))
    outbox.dismiss("c-001")

    result = main(["--project-root", str(tmp_path), "notify", "clear"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Cleared 1 dismissed" in captured.out
    assert len(outbox.list(status="dismissed")) == 0


def test_health_command_reports_missing_config(
    tmp_path: Path, capsys: CaptureFixture
) -> None:
    result = main(["--project-root", str(tmp_path), "health"])
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

    monkeypatch.setattr("sys.stdin", _TextInput(":search deep work\n:q\n"))
    monkeypatch.setattr(
        "nuself.cli.lifecycle.status",
        _mock_status,
    )
    result = main(["--project-root", str(tmp_path), "attach"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out


def test_config_command_shows_paths(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "config"])
    captured = capsys.readouterr()
    assert result == 0
    assert "project_root:" in captured.out
    assert "private_root:" in captured.out
    assert "config_path:" in captured.out
    assert "config_file:" in captured.out
    assert "config_effective:" in captured.out
    assert "llm.openai.api_key:" in captured.out


def test_memory_list_shows_entries(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Focus", body="Deep work."))

    result = main(["--project-root", str(tmp_path), "memory", "list"])
    captured = capsys.readouterr()
    assert result == 0
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

    result = main(["--project-root", str(tmp_path), "source", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Test Source" in captured.out


def test_memory_source_list_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "source", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No source documents." in captured.out


def test_memory_source_show_displays_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    doc = SourceDocument(id="src-002", path="/tmp/test.txt", title="Test Source", kind="text")
    repo.save_document(doc)

    result = main(["--project-root", str(tmp_path), "source", "show", doc.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Test Source" in captured.out


def test_memory_source_show_missing_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "source", "show", "missing-id"])
    captured = capsys.readouterr()
    assert result == 1
    assert "Source document not found: missing-id" in captured.err


def test_memory_source_delete_removes_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.source_repository import SourceRepository
    from nuself.domain.source import SourceDocument

    repo = SourceRepository(tmp_path)
    doc = SourceDocument(id="src-003", path="/tmp/test.txt", title="Test Source", kind="text")
    repo.save_document(doc)

    result = main(["--project-root", str(tmp_path), "source", "delete", doc.id])
    assert result == 0
    assert len(repo.list_documents()) == 0


def test_memory_source_chunks_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "source", "chunks", "some-id"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No source chunks." in captured.out


def test_memory_source_search_empty_shows_message(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "source", "search", "xyz"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No matching source chunks." in captured.out


def test_memory_source_extract_missing_document(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "source", "extract", "missing-id"])
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
    result = main(["--project-root", str(tmp_path), "memory", "candidate", "list"])
    captured = capsys.readouterr()
    assert result == 0
    assert "No memory candidates." in captured.out


def test_memory_candidate_list_filters_by_review_state(tmp_path: Path, capsys: CaptureFixture) -> None:
    from nuself.memory.repository import MemoryCandidateRepository
    from nuself.domain.memory import MemoryCandidate

    repo = MemoryCandidateRepository(tmp_path)
    pending = repo.save(MemoryCandidate(type="belief", title="Pending", body="Pending candidate."))
    accepted = repo.save(MemoryCandidate(type="belief", title="Accepted", body="Accepted candidate.", review_state="accepted"))

    result = main(["--project-root", str(tmp_path), "memory", "candidate", "list", "--review-state", "accepted", "--all"])
    captured = capsys.readouterr()
    assert result == 0
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

    result = main(["--project-root", str(tmp_path), "memory", "candidate", "list", "--sort-by", "importance"])
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

    result = main(["--project-root", str(tmp_path), "memory", "candidate", "show", candidate.id])
    captured = capsys.readouterr()
    assert result == 0
    assert "Focus" in captured.out
    assert "Deep work." in captured.out


def test_memory_candidate_show_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "memory", "candidate", "show", "missing-id"])
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
        ["--project-root", str(tmp_path), "memory", "candidate", "accept", candidate.id]
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
        ["--project-root", str(tmp_path), "memory", "candidate", "reject", candidate.id]
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
            "candidate",
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
        ["--project-root", str(tmp_path), "memory", "candidate", "merge", candidate.id, entry.id]
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
        ["status", "--help"],
        ["health", "--help"],
        ["config", "--help"],
        ["open", "--help"],
        ["logs", "--help"],
        ["eval", "--help"],
        ["notify", "--help"],
        ["memory", "--help"],
        ["thread", "--help"],
    ],
)
def test_top_level_subcommand_help(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 0



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
        ["notify", "list", "--help"],
        ["notify", "show", "--help"],
        ["notify", "send", "--help"],
        ["notify", "dismiss", "--help"],
        ["notify", "clear", "--help"],
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
        ["memory", "candidate", "--help"],
        ["memory", "types", "--help"],
        ["source", "--help"],
        ["memory", "reindex", "--help"],
        ["thread", "list", "--help"],
        ["thread", "show", "--help"],
        ["thread", "create", "--help"],
        ["thread", "rename", "--help"],
        ["thread", "branch", "--help"],
        ["thread", "archive", "--help"],
        ["thread", "delete", "--help"],
        ["thread", "unarchive", "--help"],
        ["thread", "archived", "--help"],
    ],
)
def test_nested_subcommand_help(argv: list[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)
    assert exc_info.value.code == 0


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
        ["memory", "candidate", "list", "--help"],
        ["memory", "candidate", "show", "--help"],
        ["memory", "candidate", "accept", "--help"],
        ["memory", "candidate", "reject", "--help"],
        ["memory", "candidate", "edit", "--help"],
        ["memory", "candidate", "merge", "--help"],
        ["source", "ingest", "--help"],
        ["source", "list", "--help"],
        ["source", "show", "--help"],
        ["source", "delete", "--help"],
        ["source", "chunks", "--help"],
        ["source", "search", "--help"],
        ["source", "extract", "--help"],
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
    result = main(["--project-root", str(tmp_path), "notify", "watch", "--interval", "1"])
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
    result = main(["--project-root", str(tmp_path), "notify", "watch"])
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
    monkeypatch.setattr("sys.stdin", _TextInput(":watch\n:q\n"))
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
    monkeypatch.setattr("sys.stdin", _TextInput(":notify watch\n:q\n"))
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
