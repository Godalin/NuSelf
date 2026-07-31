"""Tests for explicit authority resource ownership."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from nuself.application import AuthorityRuntime, AuthorityRuntimeClosedError
from nuself.config import runtime_paths
from nuself.storage import StorageCollection


class _Backend:
    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.close_calls = 0
        self.close_error = close_error

    def collection(self, name: str) -> StorageCollection:
        raise AssertionError(f"unexpected collection access: {name}")

    def transaction(self) -> AbstractContextManager[None]:
        raise AssertionError("unexpected transaction access")

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def test_authority_runtime_owns_resources_until_context_exit(
    tmp_path: Path,
) -> None:
    paths = runtime_paths(tmp_path)
    backend = _Backend()

    with AuthorityRuntime(paths, backend) as runtime:
        assert runtime.paths is paths
        assert runtime.backend is backend
        assert not runtime.closed

    assert runtime.closed
    assert backend.close_calls == 1
    with pytest.raises(AuthorityRuntimeClosedError):
        _ = runtime.backend
    with pytest.raises(AuthorityRuntimeClosedError):
        _ = runtime.paths


def test_authority_runtime_close_is_idempotent(tmp_path: Path) -> None:
    backend = _Backend()
    runtime = AuthorityRuntime(runtime_paths(tmp_path), backend)

    runtime.close()
    runtime.close()

    assert backend.close_calls == 1


def test_authority_runtime_remains_closed_when_backend_close_fails(
    tmp_path: Path,
) -> None:
    failure = RuntimeError("close failed")
    backend = _Backend(close_error=failure)
    runtime = AuthorityRuntime(runtime_paths(tmp_path), backend)

    with pytest.raises(RuntimeError, match="close failed") as raised:
        runtime.close()

    assert raised.value is failure
    assert runtime.closed
    runtime.close()
    assert backend.close_calls == 1
