"""Tests for the shared CLI/daemon application lifecycle owner."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.application.runtime import (
    ApplicationRuntimeClosedError,
    open_application_runtime,
)
from nuself.cli.composition import (
    compose_cli_application,
    use_cli_application_runtime,
)


def test_application_runtime_is_lazy_and_reuses_one_graph(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)

    assert runtime.opened is False
    first = runtime.application

    assert runtime.opened is True
    assert runtime.application is first
    assert first.paths is runtime.paths

    runtime.close()
    runtime.close()

    assert runtime.closed is True
    with pytest.raises(ApplicationRuntimeClosedError):
        _ = runtime.application


def test_cli_composition_borrows_the_scoped_runtime_graph(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)
    try:
        with use_cli_application_runtime(runtime):
            first = compose_cli_application(tmp_path)
            second = compose_cli_application(tmp_path)

        assert first is second
        assert first is runtime.application
    finally:
        runtime.close()


def test_cli_composition_rejects_authority_drift(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)
    try:
        with use_cli_application_runtime(runtime):
            with pytest.raises(RuntimeError, match="different authority"):
                compose_cli_application(tmp_path / "other")
    finally:
        runtime.close()


def test_cli_composition_requires_active_runtime(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="runtime is not active"):
        compose_cli_application(tmp_path)
