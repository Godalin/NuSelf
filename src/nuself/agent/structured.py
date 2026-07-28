"""Framework-native structured-output invocation for agent subsystems."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from nuself.agent.failover import invoke_agent_endpoint
from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.logs import LogComponent

StructuredOutputT = TypeVar(
    "StructuredOutputT",
    bound=BaseModel,
    covariant=True,
)


class StructuredAgent(Protocol[StructuredOutputT]):
    """Typed agent capability consumed by domain subsystems."""

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> StructuredOutputT: ...


class LangChainStructuredAgent(Generic[StructuredOutputT]):
    """Invoke one strict schema through LangChain with endpoint failover."""

    def __init__(
        self,
        schema: type[StructuredOutputT],
        *,
        endpoints: tuple[LangChainLLMEndpoint, ...],
        project_root: Path | None = None,
        component: LogComponent,
    ) -> None:
        self._schema = schema
        self._project_root = project_root
        self._component: LogComponent = component
        create_agent = cast(Any, _create_agent)
        self._agents = {
            endpoint.index: create_agent(
                model=endpoint.model,
                tools=[],
                response_format=ToolStrategy(schema),
            )
            for endpoint in endpoints
        }
        self._endpoints = endpoints

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> StructuredOutputT:
        def complete(endpoint: LangChainLLMEndpoint) -> StructuredOutputT:
            agent = self._agents[endpoint.index]
            result: object = agent.invoke({"messages": list(messages)})
            return self._structured_response(result)

        return invoke_agent_endpoint(
            self._endpoints,
            complete,
            project_root=self._project_root,
            component=self._component,
        )

    def _structured_response(self, result: object) -> StructuredOutputT:
        if not isinstance(result, dict):
            raise ValueError(
                "LangChain agent returned invalid state: "
                f"{type(result).__name__}"
            )
        state = cast(dict[str, object], result)
        if "structured_response" not in state:
            raise ValueError(
                "LangChain agent state is missing structured_response"
            )
        structured = state["structured_response"]
        if not isinstance(structured, self._schema):
            raise ValueError(
                "LangChain agent returned invalid structured_response: "
                f"{type(structured).__name__}"
            )
        return structured

def default_structured_agent(
    schema: type[StructuredOutputT],
    *,
    project_root: Path | None = None,
    component: LogComponent,
) -> StructuredAgent[StructuredOutputT]:
    """Build the configured framework-native runner for one schema."""
    return LangChainStructuredAgent(
        schema,
        endpoints=configured_langchain_chat_models(project_root),
        project_root=project_root,
        component=component,
    )
