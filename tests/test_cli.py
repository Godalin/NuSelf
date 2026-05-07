from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself import cli
from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.cli import main
from nuself.daemon.client import DaemonConnectionError
from nuself.daemon.protocol import DaemonResponse
from nuself.daemon.lifecycle import DaemonStatus
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence
from nuself.domain.profile import ProfileItem
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository


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
    assert "observed_at: 2026-05-07" in show_output
    assert "thread thread:default:4-6 observed_at=2026-05-07 summary=Discussed thought evolution." in show_output
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
            supersedes=[old.id],
            related_memory_ids=[related.id],
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
    source_id = list_output.split(" ", 1)[0]
    show_result = main(["--project-root", str(tmp_path), "memory", "source", "show", source_id])
    show_output = capsys.readouterr().out
    chunks_result = main(["--project-root", str(tmp_path), "memory", "source", "chunks", source_id])
    chunks_output = capsys.readouterr().out

    assert ingest_result == 0
    assert list_result == 0
    assert show_result == 0
    assert chunks_result == 0
    assert "Source ingest: documents=1 chunks=1" in ingest_output
    assert "Source Essay" in list_output
    assert "tags=mirror,imported" in list_output
    assert "privacy=shareable" in list_output
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
    list_output = capsys.readouterr().out
    source_id = list_output.split(" ", 1)[0]

    extract_result = main(["--project-root", str(tmp_path), "memory", "source", "extract", source_id])
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
    main(["--project-root", str(tmp_path), "memory", "source", "ingest", str(source_path)])
    capsys.readouterr()
    list_result = main(["--project-root", str(tmp_path), "memory", "source", "list"])
    list_output = capsys.readouterr().out
    source_id = list_output.split(" ", 1)[0]
    main(["--project-root", str(tmp_path), "memory", "source", "extract", source_id])
    capsys.readouterr()

    delete_result = main(["--project-root", str(tmp_path), "memory", "source", "delete", source_id])
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
    source_id = list_output.split(" ", 1)[0]
    main(["--project-root", str(tmp_path), "memory", "source", "extract", source_id])
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
