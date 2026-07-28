from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from nuself.cli import CliLifecycleError, main


class _Parser:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def parse_args(
        self,
        argv: object = None,
    ) -> argparse.Namespace:
        del argv
        return argparse.Namespace(project_root=self._project_root)


def test_cli_resets_default_backend_after_success(
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

    def reset_success(project_root: Path | None) -> None:
        events.append(("reset", project_root))

    monkeypatch.setattr("nuself.cli.build_parser", lambda: parser)
    monkeypatch.setattr(
        "nuself.cli.dispatch_cli",
        dispatch_success,
    )
    monkeypatch.setattr(
        "nuself.cli.reset_default_backend",
        reset_success,
    )

    assert main(["status"]) == 7
    assert events == [
        ("dispatch", tmp_path, parser),
        ("reset", tmp_path),
    ]


def test_cli_resets_backend_then_reraises_same_control_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = SystemExit(23)
    resets: list[Path | None] = []
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

    def reset_success(project_root: Path | None) -> None:
        resets.append(project_root)

    monkeypatch.setattr("nuself.cli.dispatch_cli", fail_dispatch)
    monkeypatch.setattr(
        "nuself.cli.reset_default_backend",
        reset_success,
    )

    with pytest.raises(SystemExit) as captured:
        main(["status"])

    assert captured.value is primary
    assert resets == [tmp_path]


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

    def fail_reset(project_root: Path | None) -> None:
        assert project_root == tmp_path
        raise cleanup_error

    def record_failure(
        error: Exception,
        **kwargs: object,
    ) -> None:
        del kwargs
        reports.append(error)

    monkeypatch.setattr("nuself.cli.dispatch_cli", fail_dispatch)
    monkeypatch.setattr(
        "nuself.cli.reset_default_backend",
        fail_reset,
    )
    monkeypatch.setattr(
        "nuself.cli.report_observed_failure",
        record_failure,
    )

    with pytest.raises(CliLifecycleError) as captured:
        main(["status"])

    assert captured.value.primary_error is primary
    assert captured.value.__cause__ is primary
    assert captured.value.failures[0].step == (
        "storage.default_backend.reset"
    )
    assert captured.value.failures[0].error is cleanup_error
    assert reports == [captured.value]
