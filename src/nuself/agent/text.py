"""Framework-native free-text invocation for agent subsystems."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from langchain_core.messages import BaseMessage

from nuself.agent.errors import AgentInvalidOutputError
from nuself.agent.endpoint_audit import AgentEndpointComponent
from nuself.agent.failover import invoke_agent_endpoint
from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)


class TextAgent(Protocol):
    """Natural-language agent capability consumed by domain subsystems."""

    def invoke(self, messages: Sequence[BaseMessage]) -> str: ...


class LangChainTextAgent:
    """Invoke a LangChain model for one non-empty natural-language result."""

    def __init__(
        self,
        *,
        endpoints: tuple[LangChainLLMEndpoint, ...],
        project_root: Path | None = None,
        component: AgentEndpointComponent,
    ) -> None:
        self._endpoints = endpoints
        self._project_root = project_root
        self._component: AgentEndpointComponent = component

    def invoke(self, messages: Sequence[BaseMessage]) -> str:
        def complete(endpoint: LangChainLLMEndpoint) -> str:
            result = endpoint.model.invoke(list(messages))
            text = result.text.strip()
            if not text:
                raise AgentInvalidOutputError(
                    "LangChain model returned empty text"
                )
            return text

        return invoke_agent_endpoint(
            self._endpoints,
            complete,
            project_root=self._project_root,
            component=self._component,
        )


def default_text_agent(
    *,
    project_root: Path | None = None,
    component: AgentEndpointComponent,
    endpoints: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> TextAgent:
    """Build the configured framework-native free-text runner."""
    return LangChainTextAgent(
        endpoints=(
            endpoints
            if endpoints is not None
            else configured_langchain_chat_models(project_root)
        ),
        project_root=project_root,
        component=component,
    )
