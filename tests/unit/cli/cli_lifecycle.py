from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from nuself.cli import CliLifecycleError, main
from nuself.cli.exit_codes import CliExitCode


class _Parser:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    def parse_args(
        self,
        argv: object = None,
    ) -> argparse.Namespace:
        del argv
        return argparse.Namespace(local=False, workspace=self._workspace)


class _Runtime:
    def __init__(
        self,
        project_root: Path,
        *,
        events: list[object] | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.project_root = project_root
        self._events = events
        self._close_error = close_error

    def close(self) -> None:
        if self._events is not None:
            self._events.append(("close", self.project_root))
        if self._close_error is not None:
            raise self._close_error


def test_cli_closes_application_runtime_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    parser = _Parser(tmp_path)

    def dispatch_success(
        args: argparse.Namespace,
        active_parser: object,
    ) -> int:
        events.append(
            ("dispatch", args.project_root, active_parser)
        )
        return 7

    def open_runtime(project_root: Path) -> _Runtime:
        return _Runtime(project_root, events=events)

    monkeypatch.setattr("nuself.cli.build_parser", lambda: parser)
    monkeypatch.setattr(
        "nuself.cli.dispatch_cli",
        dispatch_success,
    )
    monkeypatch.setattr(
        "nuself.cli.open_application_runtime",
        open_runtime,
    )

    assert main(["status"]) == 7
    assert events == [
        ("dispatch", tmp_path / ".nuself", parser),
        ("close", tmp_path / ".nuself"),
    ]


def test_cli_closes_runtime_then_reraises_same_control_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = SystemExit(23)
    events: list[object] = []
    monkeypatch.setattr(
        "nuself.cli.build_parser",
        lambda: _Parser(tmp_path),
    )

    def fail_dispatch(
        args: argparse.Namespace,
        parser: object,
    ) -> int:
        del args, parser
        raise primary

    def open_runtime(project_root: Path) -> _Runtime:
        return _Runtime(project_root, events=events)

    monkeypatch.setattr("nuself.cli.dispatch_cli", fail_dispatch)
    monkeypatch.setattr(
        "nuself.cli.open_application_runtime",
        open_runtime,
    )

    with pytest.raises(SystemExit) as captured:
        main(["status"])

    assert captured.value is primary
    assert events == [("close", tmp_path / ".nuself")]


def test_cli_interrupt_closes_runtime_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[object] = []
    monkeypatch.setattr(
        "nuself.cli.build_parser",
        lambda: _Parser(tmp_path),
    )

    def interrupt_dispatch(
        args: argparse.Namespace,
        parser: object,
    ) -> int:
        del args, parser
        raise KeyboardInterrupt

    def open_runtime(project_root: Path) -> _Runtime:
        return _Runtime(project_root, events=events)

    monkeypatch.setattr("nuself.cli.dispatch_cli", interrupt_dispatch)
    monkeypatch.setattr(
        "nuself.cli.open_application_runtime",
        open_runtime,
    )

    assert main(["status"]) is CliExitCode.INTERRUPTED
    assert events == [("close", tmp_path / ".nuself")]
    assert capsys.readouterr().err == "Interrupted.\n"


def test_cli_interrupt_before_scope_has_no_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt_parser() -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr("nuself.cli.build_parser", interrupt_parser)

    assert main(["status"]) is CliExitCode.INTERRUPTED
    assert capsys.readouterr().err == "Interrupted.\n"


def test_cli_cleanup_failure_retains_primary_as_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = KeyboardInterrupt()
    cleanup_error = OSError("storage close failed")
    reports: list[Exception] = []
    monkeypatch.setattr(
        "nuself.cli.build_parser",
        lambda: _Parser(tmp_path),
    )

    def fail_dispatch(
        args: argparse.Namespace,
        parser: object,
    ) -> int:
        del args, parser
        raise primary

    def record_failure(
        error: Exception,
        **kwargs: object,
    ) -> None:
        del kwargs
        reports.append(error)

    def open_runtime(project_root: Path) -> _Runtime:
        return _Runtime(
            project_root,
            close_error=cleanup_error,
        )

    monkeypatch.setattr("nuself.cli.dispatch_cli", fail_dispatch)
    monkeypatch.setattr(
        "nuself.cli.open_application_runtime",
        open_runtime,
    )
    monkeypatch.setattr(
        "nuself.cli.report_cli_cleanup_failure",
        record_failure,
    )

    with pytest.raises(CliLifecycleError) as captured:
        main(["status"])

    assert captured.value.primary_error is primary
    assert captured.value.__cause__ is primary
    assert captured.value.failures[0].step == (
        "application_runtime.close"
    )
    assert captured.value.failures[0].error is cleanup_error
    assert reports == [captured.value]
