"""Real LLM endpoint contracts using synthetic, non-private prompts only."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from typing import Literal, NoReturn

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict

from nuself.agent.chat.response import ConversationResponseSynthesizer
from nuself.agent.chat.types import ChatStructuredOutput
from nuself.agent.structured import LangChainStructuredAgent
from nuself.config.settings import ConfigSystem
from nuself.config.scope import scope_from_authority_root
from nuself.agent.endpoint import (
    LangChainLLMEndpoint,
    build_langchain_endpoint,
    configured_langchain_chat_models,
    redacted_llm_diagnostic,
)
from tests.live.matrix import LiveModelCase

pytestmark = pytest.mark.live_api

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _LiveStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["LIVE_STRUCTURED_OK"]


@pytest.fixture
def live_endpoint(
    live_model_case: LiveModelCase | None,
) -> LangChainLLMEndpoint:
    endpoints = configured_langchain_chat_models(
        PROJECT_ROOT,
        config=ConfigSystem.load_scope(
            scope_from_authority_root(PROJECT_ROOT)
        ),
    )
    if not endpoints:
        pytest.fail(
            "no configured LLM endpoint with a non-empty API key",
            pytrace=False,
        )
    template = endpoints[0]
    if live_model_case is None:
        return template
    live_model_spec = live_model_case.spec
    return build_langchain_endpoint(
        template.index,
        replace(
            template.settings,
            provider=live_model_spec.provider,
            model=live_model_spec.model,
        ),
    )


def _fail_live_layer(layer: str, error: Exception) -> NoReturn:
    pytest.fail(
        f"{layer} failed: {redacted_llm_diagnostic(error)}",
        pytrace=False,
    )


def test_live_model_transport(
    live_endpoint: LangChainLLMEndpoint,
) -> None:
    try:
        result = live_endpoint.model.invoke(
            [
                HumanMessage(
                    content=(
                        "Synthetic API health check. Reply with exactly "
                        "LIVE_TRANSPORT_OK and no other text."
                    )
                )
            ]
        )
    except Exception as exc:
        _fail_live_layer("model transport", exc)

    assert isinstance(result, AIMessage)
    assert result.text.strip() == "LIVE_TRANSPORT_OK"


def test_live_langchain_structured_output(
    live_endpoint: LangChainLLMEndpoint,
) -> None:
    agent = LangChainStructuredAgent(
        _LiveStructuredOutput,
        endpoints=(live_endpoint,),
        project_root=PROJECT_ROOT,
        component="chat",
    )
    try:
        result = agent.invoke(
            [
                HumanMessage(
                    content=(
                        "Synthetic structured-output health check. Return "
                        "status LIVE_STRUCTURED_OK."
                    )
                )
            ]
        )
    except Exception as exc:
        _fail_live_layer("LangChain structured output", exc)

    assert result.status == "LIVE_STRUCTURED_OK"


def test_live_nuself_chat_response(
    live_endpoint: LangChainLLMEndpoint,
    tmp_path: Path,
) -> None:
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=(live_endpoint,),
        tools=(),
    )
    try:
        result = synthesizer.complete(
            [
                HumanMessage(
                    content=(
                        "Synthetic NuSelf chat health check. Reply with "
                        "LIVE_CHAT_OK and no other text."
                    )
                )
            ]
        )
    except Exception as exc:
        _fail_live_layer("NuSelf chat response", exc)

    assert isinstance(result, ChatStructuredOutput)
    assert result.answer.strip() == "LIVE_CHAT_OK"
    assert "configured LLM request failed" not in result.answer


@tool
def _live_echo(value: str) -> str:
    """Return one synthetic live-test value unchanged."""

    return value


def test_live_nuself_tool_and_structured_response(
    live_endpoint: LangChainLLMEndpoint,
    tmp_path: Path,
) -> None:
    synthesizer = ConversationResponseSynthesizer(
        project_root=tmp_path,
        langchain_models=(live_endpoint,),
        tools=(_live_echo,),
    )
    try:
        result = synthesizer.complete(
            [
                HumanMessage(
                    content=(
                        "Synthetic NuSelf tool health check. Call _live_echo "
                        "with value LIVE_TOOL_OK, then reply with exactly "
                        "LIVE_TOOL_CHAT_OK and no other text."
                    )
                )
            ]
        )
    except Exception as exc:
        _fail_live_layer("NuSelf tool and structured response", exc)

    assert result.answer.strip() == "LIVE_TOOL_CHAT_OK"
    assert "configured LLM request failed" not in result.answer
