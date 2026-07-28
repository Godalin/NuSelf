import pytest

from nuself.decorators import approval_required, audit_log


def test_approval_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate user typing 'y' at the prompt and ensure stdin is a TTY.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    @audit_log("chat")
    @approval_required("chat")
    def quick(x: str) -> str:
        return f"done {x}"

    res = quick("bob")
    payload = __import__("json").loads(res)
    assert payload.get("approved") is True
    assert payload.get("component") == "chat"
    assert payload.get("result") == "done bob"


def test_approval_prompt_is_visible(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    events: list[tuple[str, str, str]] = []

    def fake_write_log_event(component: str, event: str, message: str, **kwargs: object) -> object:
        events.append((component, event, message))
        return object()

    monkeypatch.setattr("nuself.decorators.approval.write_log_event", fake_write_log_event)
    monkeypatch.setattr("nuself.decorators.approval.getpass.getuser", lambda: "tester")

    @approval_required("chat")
    def quick(x: str) -> str:
        return f"done {x}"

    res = quick("alice")
    captured = capsys.readouterr()
    assert "[chat] approval required" in captured.out
    assert "tool=quick" in captured.out
    assert "quick(alice)" in captured.out
    assert "approve? [y/N]" in captured.out
    payload = __import__("json").loads(res)
    assert payload.get("approved") is True
    assert payload.get("component") == "chat"
    assert payload.get("result") == "done alice"
    assert any(event == "approval_prompted" for _, event, _ in events)
    assert any(event == "service_tool_approved" for _, event, _ in events)
