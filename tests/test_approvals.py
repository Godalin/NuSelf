import json

import pytest

import nuself.decorators as decorators
from nuself.decorators import approval_required, audit_log


def test_decorator_package_has_no_pending_callable_registry() -> None:
    assert decorators.__all__ == ["approval_required", "audit_log"]
    assert not hasattr(decorators, "ApprovalManager")


def test_approval_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate user typing 'y' at the prompt and ensure stdin is a TTY.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    @audit_log("chat")
    @approval_required("chat")
    def quick(x: str) -> str:
        return f"done {x}"

    res = quick("bob")
    payload = json.loads(res)
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

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fake_write_log_event,
    )
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
    payload = json.loads(res)
    assert payload.get("approved") is True
    assert payload.get("component") == "chat"
    assert payload.get("result") == "done alice"
    assert any(event == "approval_prompted" for _, event, _ in events)
    assert any(event == "service_tool_approved" for _, event, _ in events)


def test_approval_audit_failures_do_not_replace_approved_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[tuple[str, str | None, object]] = []
    calls: list[str] = []

    def fail_audit_or_capture_failure(
        component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> None:
        if event != "approval_audit_failed":
            raise OSError("audit store unavailable")
        failures.append(
            (
                event,
                kwargs.get("error"),  # type: ignore[arg-type]
                kwargs.get("metadata"),
            )
        )

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_or_capture_failure,
    )
    monkeypatch.setattr("builtins.input", lambda: "yes")
    monkeypatch.setattr(
        "nuself.decorators.approval.getpass.getuser",
        lambda: "tester",
    )

    @approval_required("chat")
    def tool() -> str:
        calls.append("called")
        return "ok"

    payload = json.loads(tool())

    assert payload == {
        "approved": True,
        "component": "chat",
        "approver": "tester",
        "result": "ok",
    }
    assert calls == ["called"]
    assert failures == [
        (
            "approval_audit_failed",
            "audit store unavailable",
                {
                    "operation": "approval_prompted",
                    "tool": "tool",
                    "audit_event": "approval_prompted",
                },
        ),
        (
            "approval_audit_failed",
            "audit store unavailable",
                {
                    "operation": "service_tool_executed",
                    "tool": "tool",
                    "audit_event": "service_tool_executed",
                },
        ),
        (
            "approval_audit_failed",
            "audit store unavailable",
                {
                    "operation": "service_tool_approved",
                    "tool": "tool",
                    "audit_event": "service_tool_approved",
                },
        ),
    ]


def test_approval_prompt_audit_failure_does_not_change_decline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[object] = []

    def fail_audit_or_capture_failure(
        *args: object,
        **kwargs: object,
    ) -> None:
        if len(args) >= 2 and args[1] != "approval_audit_failed":
            raise OSError("audit store unavailable")
        failures.append(kwargs.get("metadata"))

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_or_capture_failure,
    )
    monkeypatch.setattr("builtins.input", lambda: "n")

    @approval_required("chat")
    def tool() -> str:
        raise AssertionError("declined tool must not execute")

    assert json.loads(tool()) == {
        "approved": False,
        "component": "chat",
        "result": None,
    }
    assert failures == [
        {
            "operation": "approval_prompted",
            "tool": "tool",
            "audit_event": "approval_prompted",
        },
    ]


def test_approval_diagnostic_failure_warns_without_masking_tool_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_audit_and_diagnostic(
        component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> None:
        del component, message, kwargs
        if event == "approval_audit_failed":
            raise RuntimeError("diagnostic store unavailable")
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_and_diagnostic,
    )
    monkeypatch.setattr("builtins.input", lambda: "y")

    @approval_required("chat")
    def tool() -> str:
        raise ValueError("tool failed")

    with pytest.warns(
        RuntimeWarning,
        match=(
            "chat/approval_audit_failed: audit store unavailable; "
            "structured logging failed: diagnostic store unavailable"
        ),
    ), pytest.raises(ValueError, match="tool failed"):
        tool()


def test_approval_diagnostic_failure_warns_without_replacing_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_audit_and_diagnostic(
        component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> None:
        del component, message, kwargs
        if event == "approval_audit_failed":
            raise RuntimeError("diagnostic store unavailable")
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_and_diagnostic,
    )
    monkeypatch.setattr("builtins.input", lambda: "y")
    monkeypatch.setattr(
        "nuself.decorators.approval.getpass.getuser",
        lambda: "tester",
    )

    @approval_required("chat")
    def tool() -> str:
        return "ok"

    with pytest.warns(RuntimeWarning) as warnings:
        payload = json.loads(tool())

    assert payload["result"] == "ok"
    assert len(warnings) == 3
