from __future__ import annotations

import builtins
from dataclasses import dataclass

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from nuself.runtime.feature.approval import ApprovalEffectRequest
from nuself.runtime.feature.protocol import ToolEffectRequest
from nuself.tui.approval import TerminalApprovalPort
from nuself.tui.effect import TerminalToolEffectPort


@dataclass(frozen=True)
class UnsupportedRequest(ToolEffectRequest):
    @property
    def kind(self) -> str:
        return "unsupported"


def _request() -> ApprovalEffectRequest:
    return ApprovalEffectRequest(
        component="reasoning",
        operation="reason_export",
        action="export",
        resource="reason output",
        risk="external",
        summary="export reason output",
    )


def test_terminal_approval_requires_explicit_yes(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(builtins, "input", lambda: "yes")
    monkeypatch.setattr("getpass.getuser", lambda: "tester")

    decision = TerminalApprovalPort().request(_request())

    assert decision.approved is True
    assert decision.approver == "tester"
    assert "approve? [y/N]" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("failure", "input_kind"),
    (
        (EOFError(), "eof"),
        (KeyboardInterrupt(), "interrupt"),
    ),
)
def test_terminal_approval_control_exit_is_safe_decline(
    monkeypatch: MonkeyPatch,
    failure: BaseException,
    input_kind: str,
) -> None:
    def fail() -> str:
        raise failure

    monkeypatch.setattr(builtins, "input", fail)

    decision = TerminalApprovalPort().request(_request())

    assert decision.approved is False
    assert decision.input_kind == input_kind


def test_terminal_effect_router_fails_fast_for_unknown_request() -> None:
    requested = False

    def observe_requested() -> None:
        nonlocal requested
        requested = True

    with pytest.raises(TypeError, match="does not support"):
        TerminalToolEffectPort().resolve(
            UnsupportedRequest("test", "choose"),
            on_requested=observe_requested,
        )

    assert requested is False
