from __future__ import annotations

from pathlib import Path
from typing import cast
from typing import Protocol

import pytest

import argparse

from nuself.cli import build_parser, main
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.readiness import (
    CommandRequirements,
    INITIALIZED_AUTHORITY,
    MODEL_READY,
    inspect_command_readiness,
)
from nuself.scope import resolve_scope


class TypedSubparsersAction(Protocol):
    choices: dict[str, argparse.ArgumentParser]


def test_missing_authority_reports_init_without_creating_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"

    result = main(
        ["--workspace", str(workspace), "data", "collections"]
    )

    assert result is CliExitCode.SETUP_REQUIRED
    assert not (workspace / ".nuself").exists()
    error = capsys.readouterr().err
    assert "not initialized" in error
    assert f"nuself --workspace {workspace} init" in error


def test_cli_exit_codes_are_typed_and_shell_stable() -> None:
    assert int(CliExitCode.SUCCESS) == 0
    assert int(CliExitCode.FAILURE) == 1
    assert int(CliExitCode.USAGE) == 2
    assert int(CliExitCode.SETUP_REQUIRED) == 3
    assert int(CliExitCode.TEMPORARY_FAILURE) == 4
    assert int(CliExitCode.CORRUPT_STATE) == 5
    assert int(CliExitCode.INTERRUPTED) == 130


def test_model_readiness_requires_init_first(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    scope = resolve_scope(workspace=workspace)

    failure = inspect_command_readiness(scope, MODEL_READY)

    assert failure is not None
    assert failure.code == "authority-not-initialized"


def test_initialized_data_commands_do_not_require_a_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    assert main(["--workspace", str(workspace), "init"]) == 0

    result = main(
        ["--workspace", str(workspace), "data", "collections"]
    )

    assert result == 0
    assert "memory" in capsys.readouterr().out


def test_default_entrypoint_missing_model_exits_before_daemon_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    assert main(["--workspace", str(workspace), "init"]) == 0

    def forbidden_status(_project_root: Path | None) -> object:
        raise AssertionError("daemon status must not run before readiness")

    monkeypatch.setattr(
        "nuself.cli.entrypoints.observe_daemon_status",
        forbidden_status,
    )

    result = main(["--workspace", str(workspace)])

    assert result == 3
    error = capsys.readouterr().err
    assert "No usable model endpoint" in error
    assert "${EDITOR:-vi}" in error
    assert "config.yaml" in error


def test_initialized_authority_inspection_is_side_effect_free(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    assert main(["--workspace", str(workspace), "init"]) == 0
    database = workspace / ".nuself" / "nuself.sqlite"
    before = database.stat()
    scope = resolve_scope(workspace=workspace)

    assert (
        inspect_command_readiness(scope, INITIALIZED_AUTHORITY)
        is None
    )

    after = database.stat()
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_mode == before.st_mode


def test_every_executable_parser_declares_readiness() -> None:
    pending = [build_parser()]
    executable = 0

    while pending:
        parser = pending.pop()
        handler_key = parser.get_default("handler_key")
        if isinstance(handler_key, str):
            executable += 1
            assert isinstance(
                parser.get_default("command_requirements"),
                CommandRequirements,
            )
        for action in parser._actions:  # pyright: ignore[reportPrivateUsage]
            if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
                pending.extend(
                    cast(TypedSubparsersAction, action).choices.values()
                )

    assert executable > 50
