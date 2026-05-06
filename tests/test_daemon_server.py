from __future__ import annotations

from pathlib import Path

from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.server import DaemonState, handle_request


def test_daemon_chat_uses_agent_and_persists_thread(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert isinstance(response.payload["reply"], str)
    assert "Last message: hello" in response.payload["reply"]
    assert response.payload["thread_id"] == "default"
    assert (tmp_path / "private" / "threads" / "default.json").is_file()
