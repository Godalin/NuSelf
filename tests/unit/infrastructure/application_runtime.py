"""Tests for the shared CLI/daemon application lifecycle owner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import nuself.application.runtime as runtime_module
from nuself.application.runtime import (
    ApplicationRuntimeClosedError,
    open_application_runtime,
    use_application_runtime,
)
from nuself.cli.composition import (
    compose_cli_application,
    compose_cli_backend,
)
from nuself.scope import resolve_scope


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
        "auto_backend",
        unexpected_backend,
    )

    open_application_runtime(tmp_path)

    assert opened is False


def test_application_runtime_preserves_explicit_scope(tmp_path: Path) -> None:
    scope = resolve_scope(
        workspace=tmp_path / "workspace",
        environ={"NUSELF_HOME": str((tmp_path / "user").resolve())},
    )

    runtime = open_application_runtime(scope)

    assert runtime.paths.scope is scope


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


def test_application_runtime_has_one_backend_acquisition_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MagicMock()
    graph = MagicMock()
    backend_opens = 0
    graph_compositions = 0

    def open_backend(root: Path) -> MagicMock:
        nonlocal backend_opens
        assert root == tmp_path
        backend_opens += 1
        return backend

    def compose(paths: object, selected: object) -> MagicMock:
        nonlocal graph_compositions
        del paths
        assert selected is backend
        graph_compositions += 1
        return graph

    monkeypatch.setattr(runtime_module, "auto_backend", open_backend)
    monkeypatch.setattr(runtime_module, "compose_application", compose)
    runtime = open_application_runtime(tmp_path)

    def borrow(index: int) -> object:
        return runtime.application if index % 2 else runtime.backend

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = tuple(executor.map(borrow, range(16)))

        assert backend_opens == 1
        assert graph_compositions == 1
        assert all(
            result is backend or result is graph
            for result in results
        )
    finally:
        runtime.close()


def test_application_runtime_closes_backend_after_composition_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MagicMock()

    def fail_composition(*args: object) -> None:
        raise RuntimeError("failed")

    def open_backend(root: Path) -> MagicMock:
        return backend

    monkeypatch.setattr(runtime_module, "auto_backend", open_backend)
    monkeypatch.setattr(
        runtime_module,
        "compose_application",
        fail_composition,
    )

    with pytest.raises(RuntimeError, match="failed"):
        with open_application_runtime(tmp_path) as runtime:
            _ = runtime.application

    backend.close.assert_called_once_with()


def test_cli_composition_borrows_the_scoped_runtime_graph(
    tmp_path: Path,
) -> None:
    runtime = open_application_runtime(tmp_path)
    try:
        with use_application_runtime(runtime):
            first = compose_cli_application(tmp_path)
            second = compose_cli_application(tmp_path)
            backend = compose_cli_backend(tmp_path)

        assert first is second
        assert first is runtime.application
        assert backend is runtime.backend
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
