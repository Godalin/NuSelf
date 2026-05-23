from __future__ import annotations

import time
from pathlib import Path

from nuself.agent.chat import ChatAgent
from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.server import DaemonState, handle_request
from nuself.llm import ChatMessage
from nuself.memory.curator import MemoryCuratorResult
from nuself.notification import NotificationOutbox, OutboxEntry


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


def test_daemon_chat_runs_memory_curator_after_reply(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = FakeChangedCurator()  # type: ignore[assignment]
    request = DaemonRequest(type="chat", payload={"message": "remember this"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["memory_update"] == "processed=2 created=1 updated=0 ignored=0"


def test_daemon_ping_returns_pong(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="ping", payload={}, request_id="ping1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["message"] == "pong"


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
