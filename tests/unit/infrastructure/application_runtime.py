"""Tests for the shared CLI/daemon application lifecycle owner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import nuself.application.runtime as runtime_module
from nuself.application.runtime import (
    ApplicationRuntimeClosedError,
    open_application_runtime,
    use_application_runtime,
)
from nuself.cli.composition import (
    compose_cli_application,
)


def test_application_runtime_factory_does_not_open_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = False

    def unexpected_backend(project_root: Path):
        nonlocal opened
        opened = True
        raise AssertionError("storage opened during runtime construction")

    monkeypatch.setattr(
        runtime_module,
        "get_default_backend",
        unexpected_backend,
    )

    open_application_runtime(tmp_path)

    assert opened is False


def test_application_runtime_reuses_one_graph_and_closes_idempotently(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)

    first = runtime.application

    assert runtime.application is first
    assert first.paths is runtime.paths

    runtime.close()
    runtime.close()

    with pytest.raises(ApplicationRuntimeClosedError):
        _ = runtime.application


def test_application_runtime_serializes_first_graph_access(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)

    def load_graph(_: int):
        return runtime.application

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            graphs = tuple(
                executor.map(load_graph, range(16))
            )

        assert all(graph is graphs[0] for graph in graphs)
    finally:
        runtime.close()


def test_cli_composition_borrows_the_scoped_runtime_graph(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)
    try:
        with use_application_runtime(runtime):
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
        with use_application_runtime(runtime):
            with pytest.raises(RuntimeError, match="different authority"):
                compose_cli_application(tmp_path / "other")
    finally:
        runtime.close()


def test_cli_composition_requires_active_runtime(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="runtime is not active"):
        compose_cli_application(tmp_path)
