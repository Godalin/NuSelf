from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from nuself.runtime.frontend import ApprovalRequest
from nuself.tui.approval import TerminalApprovalPort


def _request() -> ApprovalRequest:
    return ApprovalRequest(
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
