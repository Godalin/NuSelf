from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from nuself.agent import endpoint_audit
from nuself.agent import failover as failover_module
from nuself.agent.errors import AgentInvalidOutputError
from nuself.agent.text import LangChainTextAgent
from nuself.llm import LLMSettings, LangChainLLMEndpoint


class _FakeModel:
    def __init__(self, results: Sequence[BaseMessage | Exception]) -> None:
        self._results = iter(results)
        self.calls: list[list[BaseMessage]] = []

    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        self.calls.append(messages)
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result


class _HttpStatusError(RuntimeError):
    status_code = 429


def _endpoint(
    index: int,
    model: _FakeModel,
) -> LangChainLLMEndpoint:
    return LangChainLLMEndpoint(
        index=index,
        settings=LLMSettings(
            base_url=f"https://endpoint-{index}.example/v1",
            api_key="test",
            model=f"model-{index}",
        ),
        model=cast(BaseChatModel, model),
    )


def test_text_agent_returns_stripped_natural_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _FakeModel([AIMessage(content="  natural conclusion  ")])
    successes: list[int] = []

    def record_success(
        project_root: Path | None,
        endpoint_index: int,
    ) -> None:
        del project_root
        successes.append(endpoint_index)

    monkeypatch.setattr(
        failover_module,
        "record_llm_endpoint_success",
        record_success,
    )
    agent = LangChainTextAgent(
        endpoints=(_endpoint(3, model),),
        component="persona",
    )

    result = agent.invoke([HumanMessage(content="question")])

    assert result == "natural conclusion"
    assert successes == [3]
    assert model.calls[0][0].text == "question"


def test_text_agent_rejects_empty_result_without_failover() -> None:
    primary = _FakeModel([AIMessage(content="  ")])
    secondary = _FakeModel([AIMessage(content="unused")])
    agent = LangChainTextAgent(
        endpoints=(
            _endpoint(0, primary),
            _endpoint(1, secondary),
        ),
        component="persona",
    )

    with pytest.raises(AgentInvalidOutputError, match="empty text"):
        agent.invoke([HumanMessage(content="question")])

    assert len(primary.calls) == 1
    assert secondary.calls == []


def test_text_agent_uses_shared_endpoint_failover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = _FakeModel([_HttpStatusError("provider failure")])
    secondary = _FakeModel([AIMessage(content="fallback conclusion")])
    events: list[tuple[str, str]] = []

    def report_failure(
        error: BaseException,
        **kwargs: object,
    ) -> None:
        del error
        events.append(
            (str(kwargs["event"]), str(kwargs["status"]))
        )

    def record_success(
        project_root: Path | None,
        endpoint_index: int,
    ) -> None:
        del project_root, endpoint_index

    monkeypatch.setattr(
        endpoint_audit,
        "report_observed_failure",
        report_failure,
    )
    monkeypatch.setattr(
        failover_module,
        "record_llm_endpoint_success",
        record_success,
    )
    agent = LangChainTextAgent(
        endpoints=(
            _endpoint(0, primary),
            _endpoint(1, secondary),
        ),
        component="persona",
    )

    result = agent.invoke([HumanMessage(content="question")])

    assert result == "fallback conclusion"
    assert events == [("llm_endpoint_failed_over", "failed_over")]
