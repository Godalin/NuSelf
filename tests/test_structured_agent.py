from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict

from nuself.agent import failover as failover_module
from nuself.agent import structured as structured_module
from nuself.agent.structured import LangChainStructuredAgent
from nuself.llm import LLMSettings, LangChainLLMEndpoint


class ExampleOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    answer: str


class OtherOutput(BaseModel):
    value: str


class StubAgent:
    def __init__(
        self,
        invoke: Callable[[object], object],
    ) -> None:
        self._invoke = invoke

    def invoke(self, input: object) -> object:
        return self._invoke(input)


def _endpoint(index: int) -> LangChainLLMEndpoint:
    return LangChainLLMEndpoint(
        index=index,
        settings=LLMSettings(
            base_url=f"https://endpoint-{index}.example/v1",
            api_key="test",
            model=f"model-{index}",
        ),
        model=cast(BaseChatModel, object()),
    )


def test_structured_agent_returns_actual_schema_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ExampleOutput(answer="typed")
    successes: list[int] = []

    def create_agent(**kwargs: object) -> StubAgent:
        assert kwargs["tools"] == []
        return StubAgent(
            lambda input: {
                "structured_response": expected,
                "input": input,
            }
        )

    def record_success(
        project_root: Path | None,
        endpoint_index: int,
    ) -> None:
        successes.append(endpoint_index)

    monkeypatch.setattr(structured_module, "_create_agent", create_agent)
    monkeypatch.setattr(
        failover_module,
        "record_llm_endpoint_success",
        record_success,
    )
    runner = LangChainStructuredAgent(
        ExampleOutput,
        endpoints=(_endpoint(2),),
        project_root=tmp_path,
        component="memory",
    )

    result = runner.invoke([HumanMessage(content="classify")])

    assert result is expected
    assert successes == [2]


@pytest.mark.parametrize(
    "state",
    [
        None,
        {},
        {"structured_response": {"answer": "dictionary"}},
        {"structured_response": OtherOutput(value="wrong schema")},
    ],
)
def test_structured_agent_rejects_invalid_framework_state(
    state: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def create_agent(**kwargs: object) -> StubAgent:
        return StubAgent(lambda input: state)

    monkeypatch.setattr(
        structured_module,
        "_create_agent",
        create_agent,
    )
    runner = LangChainStructuredAgent(
        ExampleOutput,
        endpoints=(_endpoint(0),),
        component="memory",
    )

    with pytest.raises(ValueError):
        runner.invoke([HumanMessage(content="classify")])


def test_structured_agent_fails_over_only_for_endpoint_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ExampleOutput(answer="second endpoint")
    agents = iter(
        (
            StubAgent(
                lambda input: (_ for _ in ()).throw(
                    RuntimeError("HTTP 429 rate limit")
                )
            ),
            StubAgent(lambda input: {"structured_response": expected}),
        )
    )
    events: list[tuple[str, str]] = []

    def create_agent(**kwargs: object) -> StubAgent:
        return next(agents)

    def report_failure(
        error: BaseException,
        **kwargs: object,
    ) -> None:
        events.append(
            (str(kwargs["event"]), str(kwargs["status"]))
        )

    def record_success(
        project_root: Path | None,
        endpoint_index: int,
    ) -> None:
        return None

    monkeypatch.setattr(
        structured_module,
        "_create_agent",
        create_agent,
    )
    monkeypatch.setattr(
        failover_module,
        "report_observed_failure",
        report_failure,
    )
    monkeypatch.setattr(
        failover_module,
        "record_llm_endpoint_success",
        record_success,
    )
    runner = LangChainStructuredAgent(
        ExampleOutput,
        endpoints=(_endpoint(0), _endpoint(1)),
        component="memory",
    )

    result = runner.invoke([HumanMessage(content="classify")])

    assert result is expected
    assert events == [("llm_endpoint_failed_over", "failed_over")]


def test_structured_agent_does_not_fail_over_protocol_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = 0
    invoked: list[int] = []

    def create_agent(**kwargs: object) -> StubAgent:
        nonlocal created
        position = created
        created += 1

        def invoke(input: object) -> object:
            invoked.append(position)
            return {}

        return StubAgent(invoke)

    monkeypatch.setattr(structured_module, "_create_agent", create_agent)
    runner = LangChainStructuredAgent(
        ExampleOutput,
        endpoints=(_endpoint(0), _endpoint(1)),
        component="memory",
    )

    with pytest.raises(
        ValueError,
        match="missing structured_response",
    ):
        runner.invoke([HumanMessage(content="classify")])

    assert invoked == [0]


def test_shared_endpoint_runner_rejects_invalid_attempt_count() -> None:
    with pytest.raises(
        ValueError,
        match="attempts_per_endpoint must be at least 1",
    ):
        failover_module.invoke_agent_endpoint(
            (_endpoint(0),),
            lambda endpoint: endpoint,
            project_root=None,
            component="memory",
            attempts_per_endpoint=0,
        )


@pytest.mark.parametrize(
    "error",
    [
        AssertionError(),
        AttributeError(),
        ImportError(),
        KeyError(),
        IndexError(),
        MemoryError(),
        NameError(),
        NotImplementedError(),
        RecursionError(),
        SyntaxError(),
        SystemError(),
        TypeError(),
    ],
    ids=[
        "assertion",
        "attribute",
        "import",
        "key",
        "index",
        "memory",
        "name",
        "not-implemented",
        "recursion",
        "syntax",
        "system",
        "type",
    ],
)
def test_shared_agent_policy_rejects_implementation_errors(
    error: Exception,
) -> None:
    assert not failover_module.is_recoverable_agent_failure(error)


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(),
        ValueError(),
        OSError(),
        Exception(),
    ],
    ids=["runtime", "validation", "operating-system", "provider-specific"],
)
def test_shared_agent_policy_accepts_recoverable_failures(
    error: Exception,
) -> None:
    assert failover_module.is_recoverable_agent_failure(error)
