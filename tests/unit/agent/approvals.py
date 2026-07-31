import json

import pytest

import nuself.decorators as decorators
from nuself.decorators import approval_required
from nuself.runtime.messages import RuntimeEnvelope


def test_decorator_package_has_no_pending_callable_registry() -> None:
    assert "tool" in decorators.__all__
    assert "requires_confirmation" in decorators.__all__
    assert not hasattr(decorators, "pending_approvals")
    assert not hasattr(decorators, "ApprovalManager")


def test_approval_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate user typing 'y' at the prompt and ensure stdin is a TTY.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

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

    def fake_write_log_event(
        envelope: RuntimeEnvelope,
        **_kwargs: object,
    ) -> object:
        events.append(
            (
                envelope.producer,  # type: ignore[union-attr]
                envelope.name,  # type: ignore[union-attr]
                envelope.payload["message"],  # type: ignore[union-attr]
            )
        )
        return object()

    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
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
    assert any(event == "approval_decided" for _, event, _ in events)


def test_approval_decision_is_observed_before_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr("builtins.input", lambda: "yes")
    monkeypatch.setattr(
        "nuself.decorators.approval.getpass.getuser",
        lambda: "tester",
    )

    def capture(envelope: RuntimeEnvelope, **_kwargs: object) -> object:
        order.append(envelope.name)  # type: ignore[union-attr]
        return object()

    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        capture,
    )

    @approval_required("chat")
    def tool() -> str:
        order.append("tool_body")
        return "ok"

    tool()

    assert order == [
        "approval_prompted",
        "approval_decided",
        "tool_body",
    ]


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
        if event != "observability_projection_failed":
            raise OSError("audit store unavailable")
        failures.append(
            (
                event,
                kwargs.get("error"),  # type: ignore[arg-type]
                kwargs.get("metadata"),
            )
        )

    def fail_audit_envelope(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_or_capture_failure,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_audit_envelope,
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
                "observability_projection_failed",
                "audit store unavailable",
                {"failed_event": "approval_prompted"},
        ),
        (
                "observability_projection_failed",
                "audit store unavailable",
                {"failed_event": "approval_decided"},
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
        if (
            len(args) >= 2
            and args[1] != "observability_projection_failed"
        ):
            raise OSError("audit store unavailable")
        failures.append(kwargs.get("metadata"))

    def fail_audit_envelope(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_or_capture_failure,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_audit_envelope,
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
        {"failed_event": "approval_prompted"},
        {"failed_event": "approval_decided"},
    ]


def test_approval_eof_uses_safe_default_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    decisions: list[object] = []

    def end_input() -> str:
        raise EOFError("stdin closed")

    monkeypatch.setattr("builtins.input", end_input)

    def capture(envelope: RuntimeEnvelope, **_kwargs: object) -> object:
        if envelope.name == "approval_decided":
            decisions.append(envelope.payload["metadata"])
        return object()

    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        capture,
    )

    @approval_required("chat")
    def tool() -> str:
        calls.append("called")
        return "unexpected"

    assert json.loads(tool()) == {
        "approved": False,
        "component": "chat",
        "result": None,
    }
    assert calls == []
    assert decisions == [
        {
            "tool": "tool",
            "approved": False,
            "approver": None,
            "input_kind": "eof",
        }
    ]


def test_approval_interrupt_uses_safe_default_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decisions: list[object] = []

    def interrupt() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)

    def capture(envelope: RuntimeEnvelope, **_kwargs: object) -> object:
        if envelope.name == "approval_decided":
            decisions.append(envelope.payload["metadata"])
        return object()

    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        capture,
    )

    @approval_required("chat")
    def tool() -> str:
        raise AssertionError("interrupted approval must not execute")

    assert json.loads(tool())["approved"] is False
    assert decisions == [
        {
            "tool": "tool",
            "approved": False,
            "approver": None,
            "input_kind": "interrupt",
        }
    ]


def test_approval_render_failure_propagates_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_render(*args: object, **kwargs: object) -> str:
        del args, kwargs
        raise RuntimeError("approval renderer broken")

    monkeypatch.setattr(
        "nuself.tui.render.render_approval_prompt",
        fail_render,
    )

    @approval_required("chat")
    def tool() -> str:
        calls.append("called")
        return "unexpected"

    with pytest.raises(RuntimeError, match="approval renderer broken"):
        tool()

    assert calls == []


def test_approval_output_failure_propagates_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_print(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("approval terminal unavailable")

    monkeypatch.setattr("builtins.print", fail_print)

    @approval_required("chat")
    def tool() -> str:
        calls.append("called")
        return "unexpected"

    with pytest.raises(OSError, match="approval terminal unavailable"):
        tool()

    assert calls == []


def test_approval_unexpected_input_failure_propagates_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_input() -> str:
        raise RuntimeError("approval input broken")

    monkeypatch.setattr("builtins.input", fail_input)

    @approval_required("chat")
    def tool() -> str:
        calls.append("called")
        return "unexpected"

    with pytest.raises(RuntimeError, match="approval input broken"):
        tool()

    assert calls == []


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
        if event == "observability_projection_failed":
            raise RuntimeError("diagnostic store unavailable")
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_and_diagnostic,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_audit_and_diagnostic,
    )
    monkeypatch.setattr("builtins.input", lambda: "y")

    @approval_required("chat")
    def tool() -> str:
        raise ValueError("tool failed")

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
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
        if event == "observability_projection_failed":
            raise RuntimeError("diagnostic store unavailable")
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_and_diagnostic,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
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
    assert len(warnings) == 2
