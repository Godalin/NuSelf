"""Explicit opt-in boundary for real-provider tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-api",
        action="store_true",
        default=False,
        help="send fixed synthetic prompts to the configured real LLM endpoint",
    )


@pytest.fixture(scope="session", autouse=True)
def require_live_api_opt_in(
    request: pytest.FixtureRequest,
) -> Generator[None]:
    if not request.config.getoption("--run-live-api"):
        pytest.skip(
            "live API tests require explicit --run-live-api opt-in",
        )
    yield
