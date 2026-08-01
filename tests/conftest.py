from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.backend import begin_backend_scope, end_backend_scope


@pytest.fixture(autouse=True)
def _owned_backends() -> Generator[None]:  # pyright: ignore[reportUnusedFunction]
    token = begin_backend_scope()
    try:
        yield
    finally:
        end_backend_scope(token)
