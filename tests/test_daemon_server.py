from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from nuself.agent.chat import ChatAgent
from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.server import (
    DaemonState,
    DaemonWorkerJoinTimeoutError,
    handle_request,
)
from nuself.llm import ChatMessage
from nuself.logs import read_log_events
from nuself.memory.curator import MemoryCuratorResult
from nuself.notification import NotificationOutbox, OutboxEntry
from nuself.runtime.context import RuntimeContext, current_runtime_context
from nuself.runtime.workers import OwnedWorker


class StructuredFakeLLM:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return (
            '{"answer":"stubbed: hello","evidence_references":["mem_1","source:note:0"],'
            '"confidence":0.8,"epistemic_status":"grounded"}'
        )


class FailingLLM:
    def complete(self, messages: list[ChatMessage]) -> str:
        raise RuntimeError("llm unavailable")


class RepeatedChainFailingLLM:
    def complete(self, messages: list[ChatMessage]) -> str:
        try:
            raise RuntimeError("same")
        except RuntimeError as exc:
            raise RuntimeError("same") from exc


def test_daemon_chat_uses_agent_and_persists_thread(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.chat_agent = ChatAgent(tmp_path, llm=StructuredFakeLLM())
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert isinstance(response.payload["reply"], str)
    assert response.payload["reply"] == "stubbed: hello"
    assert response.payload["answer"] == response.payload["reply"]
    assert response.payload["evidence_references"] == ["mem_1", "source:note:0"]
    assert response.payload["confidence"] == 0.8
    assert response.payload["epistemic_status"] == "grounded"
    assert response.payload["thread_id"] == "default"
    assert "node_trace" not in response.payload
    assert (tmp_path / "private" / "threads" / "default.json").is_file()


def test_daemon_chat_uses_explicit_thread_id(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.chat_agent = ChatAgent(tmp_path, llm=StructuredFakeLLM())
    request = DaemonRequest(type="chat", payload={"message": "hello", "thread_id": "custom"}, request_id="chat2")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["thread_id"] == "custom"
    assert (tmp_path / "private" / "threads" / "custom.json").is_file()


def test_daemon_chat_persists_turn_id_for_retry_idempotency(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.chat_agent = ChatAgent(tmp_path, llm=StructuredFakeLLM())
    request = DaemonRequest(
        type="chat",
        payload={"message": "hello", "thread_id": "default", "turn_id": "turn-retry"},
        request_id="chat-turn-id",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    stored = (tmp_path / "private" / "threads" / "default.json").read_text(encoding="utf-8")
    assert '"turn_id": "turn-retry"' in stored


def test_daemon_chat_error_includes_root_cause(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.chat_agent = ChatAgent(tmp_path, llm=FailingLLM())
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat-fail")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "conversation graph node 'respond' failed" in response.error
    assert "llm unavailable" in response.error


def test_daemon_chat_error_preserves_repeated_exception_messages(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.chat_agent = ChatAgent(tmp_path, llm=RepeatedChainFailingLLM())
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat-repeat-fail")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert response.error.count("same") == 2


class FakeChangedCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        return MemoryCuratorResult(
            processed_messages=2,
            created=1,
            updated=0,
            ignored=0,
            log_path=Path("memory.log"),
        )


class RecoverableFailingCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        try:
            raise RuntimeError("curator backend unavailable")
        except RuntimeError as exc:
            raise RuntimeError("post-chat curation failed") from exc


class UnexpectedFailingCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        raise ValueError("curator invariant broken")


def test_daemon_chat_runs_memory_curator_after_reply(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = FakeChangedCurator()  # type: ignore[assignment]
    request = DaemonRequest(type="chat", payload={"message": "remember this"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["memory_update"] == "processed=2 created=1 updated=0 ignored=0"


def test_daemon_chat_observes_recoverable_curator_failure(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = RecoverableFailingCurator()  # type: ignore[assignment]
    request = DaemonRequest(
        type="chat",
        payload={
            "message": "remember this",
            "thread_id": "project",
            "turn_id": "turn-curator-failure",
        },
        request_id="chat-curator-failure",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    assert "memory_update" not in response.payload
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "post_chat_curation_failed"
    assert event.status == "degraded"
    assert event.error == (
        "post-chat curation failed <- curator backend unavailable"
    )
    assert event.request_id == "chat-curator-failure"
    assert event.thread_id == "project"
    assert event.turn_id == "turn-curator-failure"
    assert event.source == "daemon"


def test_daemon_chat_does_not_degrade_unexpected_curator_failure(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = UnexpectedFailingCurator()  # type: ignore[assignment]
    request = DaemonRequest(
        type="chat",
        payload={"message": "remember this"},
        request_id="chat-curator-invariant",
    )

    with pytest.raises(ValueError, match="curator invariant broken"):
        handle_request(request, state)


def test_daemon_ping_returns_pong(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="ping", payload={}, request_id="ping1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["message"] == "pong"


def test_daemon_health_returns_worker_snapshots(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    response = handle_request(
        DaemonRequest(type="health", payload={}, request_id="health1"),
        state,
    )
    assert response.status == "ok"
    workers = response.payload["workers"]
    assert isinstance(workers, list)
    names: set[str] = set()
    for item in workers:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str):
                names.add(name)
    assert names == {
        "memory_curator",
        "reflection_scheduler",
        "reason_scheduler",
        "export_worker",
        "notification_delivery",
    }


def test_memory_curator_worker_survives_unexpected_error(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator_interval_seconds = 0.01

    class BrokenCurator:
        def run_once(self) -> None:
            raise ValueError("bad curator data")

    state.memory_curator = BrokenCurator()  # type: ignore[assignment]
    state.start_background_memory_curator()
    deadline = time.monotonic() + 1.0
    health = state.worker_health()[0]
    while health.consecutive_failures == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
        health = state.worker_health()[0]

    assert health.alive is True
    assert health.consecutive_failures >= 1
    assert health.last_error == "bad curator data"
    state.shutdown_requested.set()
    state.stop_background_memory_curator()


def test_worker_supervisor_records_escaping_target_and_context(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    observed: list[RuntimeContext] = []

    def fail_target() -> None:
        observed.append(current_runtime_context())
        raise ValueError("target escaped")

    state._workers["memory_curator"] = OwnedWorker(  # pyright: ignore[reportPrivateUsage]
        name="memory_curator",
        thread_name="test-supervised-worker",
        target=state._supervised_worker_target(  # pyright: ignore[reportPrivateUsage]
            "memory_curator",
            fail_target,
        ),
    )

    state.start_background_memory_curator()
    state._join_worker(  # pyright: ignore[reportPrivateUsage]
        "memory_curator",
        timeout=1,
    )

    assert observed[0].source == "daemon.worker.memory_curator"
    health = next(
        item for item in state.worker_health() if item.name == "memory_curator"
    )
    assert health.alive is False
    assert health.consecutive_failures == 1
    assert health.last_error == "target escaped"
    event = next(
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event == "worker_exited_unexpectedly"
    )
    assert event.source == "daemon.worker.memory_curator"
    assert event.metadata == {"worker": "memory_curator"}
    assert event.error == "target escaped"


def test_worker_error_log_failure_does_not_stop_scheduled_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.runtime import observability

    state = DaemonState(tmp_path)
    state.memory_curator_interval_seconds = 0.01
    calls = 0

    class FailOnceCurator:
        def run_once(self) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("first iteration failed")
            state.shutdown_requested.set()

    state.memory_curator = FailOnceCurator()  # type: ignore[assignment]

    def fail_error_log(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise OSError("worker log unavailable")

    monkeypatch.setattr(
        observability,
        "write_log_event",
        fail_error_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="memory_curator_error.*worker log unavailable",
    ):
        state.start_background_memory_curator()
        state.stop_background_memory_curator()

    assert calls == 2
    health = next(
        item for item in state.worker_health() if item.name == "memory_curator"
    )
    assert health.alive is False
    assert health.consecutive_failures == 0
    assert health.last_success_at is not None


def test_export_worker_initialization_fails_before_thread_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import server as server_mod

    state = DaemonState(tmp_path)

    def fail_store(*args: object, **kwargs: object) -> object:
        raise OSError("workspace unavailable")

    monkeypatch.setattr(server_mod, "PrivateWorkspaceStore", fail_store)

    with pytest.raises(OSError, match="workspace unavailable"):
        state.start_background_export_worker()

    snapshot = state._workers[  # pyright: ignore[reportPrivateUsage]
        "export_worker"
    ].snapshot
    assert snapshot.state == "new"
    assert snapshot.alive is False


def test_daemon_worker_join_timeout_is_logged_and_remains_live(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    release = threading.Event()

    def wait_for_release() -> None:
        release.wait()

    state._workers["memory_curator"] = OwnedWorker(  # pyright: ignore[reportPrivateUsage]
        name="memory_curator",
        thread_name="test-memory-curator",
        target=wait_for_release,
    )
    state.start_background_memory_curator()
    with pytest.raises(
        DaemonWorkerJoinTimeoutError,
        match="memory_curator did not stop",
    ):
        state._join_worker(  # pyright: ignore[reportPrivateUsage]
            "memory_curator",
            timeout=0,
        )

    health = next(
        item for item in state.worker_health() if item.name == "memory_curator"
    )
    assert health.alive is True
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "thread_timeout"
    assert event.status == "timed_out"
    assert event.metadata == {
        "worker": "memory_curator",
        "timeout_seconds": 0,
        "lifecycle_state": "timed_out",
    }

    release.set()
    state._join_worker(  # pyright: ignore[reportPrivateUsage]
        "memory_curator",
        timeout=1,
    )
    health = next(
        item for item in state.worker_health() if item.name == "memory_curator"
    )
    assert health.alive is False


def test_daemon_echo_returns_payload(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="echo", payload={"test": "data"}, request_id="echo1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["test"] == "data"


def test_daemon_shutdown_sets_flag(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="shutdown", payload={}, request_id="shutdown1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["message"] == "shutdown requested"
    assert state.shutdown_requested.is_set()


def test_daemon_unsupported_type_returns_error(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="unknown", payload={}, request_id="unknown1")  # type: ignore[arg-type]

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "unsupported request type" in response.error


def test_daemon_chat_rejects_non_string_message(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": 123}, request_id="chat_bad")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "requires string payload field 'message'" in response.error


def test_daemon_handle_backstops_unexpected_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unexpected (non-ProtocolError) failure in request handling must still
    return a failed response with the exception chain, not hang the client."""
    import io
    from types import SimpleNamespace

    from nuself.daemon import server as server_mod
    from nuself.daemon.protocol import DaemonResponse

    raw = DaemonRequest(type="ping", payload={}, request_id="boom1").to_json_line()
    fake = SimpleNamespace(
        rfile=io.BytesIO(raw),
        wfile=io.BytesIO(),
        _daemon_state=lambda: SimpleNamespace(project_root=tmp_path),
    )

    def boom(request: DaemonRequest, state: object) -> DaemonResponse:
        raise ValueError("kaboom")

    monkeypatch.setattr(server_mod, "handle_request", boom)

    server_mod.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(fake.wfile.getvalue())
    assert response.status == "error"
    assert response.error is not None
    assert "kaboom" in response.error


def test_daemon_background_reflection_scheduler_creates_outbox_entry(tmp_path: Path) -> None:
    """End-to-end: daemon starts reflection scheduler thread, which reflects and creates an outbox entry."""
    state = DaemonState(tmp_path)
    state.reflection_check_interval_seconds = 0.05

    class MockScheduler:
        def should_reflect(self, now: object = None) -> bool:
            return True

        def reflect(self, now: object = None) -> bool:
            outbox = NotificationOutbox(tmp_path)
            outbox.add(
                OutboxEntry(
                    id="reflection-test-001",
                    title="test reflection idea",
                    body="test body",
                    status="pending",
                    idempotency_key="reflection-test-key",
                )
            )
            return True

    state.reflection_scheduler = MockScheduler()  # type: ignore[assignment]
    state.start_background_reflection_scheduler()

    time.sleep(0.15)

    state.shutdown_requested.set()
    state.stop_background_reflection_scheduler()

    outbox = NotificationOutbox(tmp_path)
    entries = outbox.list()
    assert len(entries) >= 1
    assert any(e.title == "test reflection idea" for e in entries)
