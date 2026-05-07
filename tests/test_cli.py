from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself import cli
from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.cli import main
from nuself.daemon.client import DaemonConnectionError
from nuself.daemon.protocol import DaemonResponse
from nuself.daemon.lifecycle import DaemonStatus
from nuself.domain.memory import MemoryCandidate, MemoryEntry
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository


class CaptureResult(Protocol):
    out: str
    err: str


class CaptureFixture(Protocol):
    def readouterr(self) -> CaptureResult: ...


class MonkeyPatchFixture(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


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


def test_chat_uses_one_shot_when_daemon_is_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
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
    assert "Memory preview (1/1):" in captured.out
    assert "Clarity" in captured.out
    assert "State assumptions explicitly." in captured.out


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
    assert "Creating new daemon..." in captured.out
    assert "Created daemon:" in captured.out
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
    assert "Memory preview (1/2):" in captured.out
    assert "... 1 more." in captured.out


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
    entry_id = add_output.split(" ", 1)[0]

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
    entry_id = add_output.split(" ", 1)[0]

    entry = MemoryEntryRepository(tmp_path).get(entry_id)

    assert add_result == 0
    assert entry.type == "preference"
    assert entry.title.startswith("I prefer terse CLI summaries")
    assert entry.title.endswith("...")
    assert entry.body == "I prefer terse CLI summaries with concrete next steps."


def test_memory_candidate_review_flow_accepts_temporal_candidate(tmp_path: Path, capsys: CaptureFixture) -> None:
    candidate = MemoryCandidateRepository(tmp_path).save(
        MemoryCandidate(
            type="belief",
            title="Temporal memory",
            body="Memory should preserve when a view was observed.",
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
    assert "observed_at: 2026-05-07" in show_output
    assert "Accepted memory candidate:" in accept_output
    assert entries[0].observed_at == "2026-05-07"
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
