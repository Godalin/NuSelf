"""Explicit opt-in boundary for real-provider tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest
from _pytest.mark.structures import ParameterSet

from nuself.live_testing import (
    LiveCapability,
    LiveModelCase,
    select_live_model_cases,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-api",
        action="store_true",
        default=False,
        help="send fixed synthetic prompts to the configured real LLM endpoint",
    )
    parser.addoption(
        "--live-model",
        action="append",
        default=[],
        metavar="PROVIDER:MODEL",
        help=(
            "repeat to test an explicit model matrix with the configured "
            "base URL and credential"
        ),
    )
    parser.addoption(
        "--live-opencode-go-matrix",
        action="store_true",
        default=False,
        help="run the documented strict OpenCode Go capability matrix",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "live_model_case" not in metafunc.fixturenames:
        return
    raw_option: object = metafunc.config.getoption("live_model")
    if not isinstance(raw_option, list):
        raise pytest.UsageError("--live-model option state is invalid")
    raw_values = cast(list[object], raw_option)
    try:
        matrix = select_live_model_cases(
            [str(value) for value in raw_values],
            opencode_go_matrix=bool(
                metafunc.config.getoption(
                    "live_opencode_go_matrix"
                )
            ),
        )
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
    parameters: tuple[LiveModelCase | None, ...] = matrix or (None,)
    capability = _test_capability(metafunc.function.__name__)
    case_parameters: list[ParameterSet] = [
        _case_parameter(item, capability)
        for item in parameters
    ]
    metafunc.parametrize(
        "live_model_case",
        cast(list[object], case_parameters),
    )


def _test_capability(test_name: str) -> LiveCapability:
    capabilities: dict[str, LiveCapability] = {
        "test_live_model_transport": "transport",
        "test_live_langchain_structured_output": "structured",
        "test_live_nuself_chat_response": "chat",
        "test_live_nuself_tool_and_structured_response": "tool",
    }
    try:
        return capabilities[test_name]
    except KeyError as exc:
        raise pytest.UsageError(
            f"live model case has no capability mapping for {test_name}"
        ) from exc


def _case_parameter(
    case: LiveModelCase | None,
    capability: LiveCapability,
) -> ParameterSet:
    if case is None:
        return pytest.param(None, id="configured")
    marks: tuple[pytest.MarkDecorator, ...] = ()
    if capability in case.unsupported:
        marks = (
            pytest.mark.xfail(
                strict=True,
                reason=(
                    f"{case.spec.id} does not currently satisfy "
                    f"the {capability} live contract"
                ),
            ),
        )
    elif capability in case.unstable:
        marks = (
            pytest.mark.xfail(
                strict=False,
                reason=(
                    f"{case.spec.id} has an observed unstable "
                    f"{capability} live contract"
                ),
            ),
        )
    return pytest.param(
        case,
        id=case.spec.id,
        marks=marks,
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
