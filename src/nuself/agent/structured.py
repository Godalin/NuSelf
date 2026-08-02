"""Framework-native structured-output invocation for agent subsystems."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from nuself.agent.errors import AgentInvalidOutputError, AgentProtocolError
from nuself.agent.endpoint_audit import AgentEndpointComponent
from nuself.agent.failover import invoke_agent_endpoint
from nuself.agent.endpoint import (
    LangChainLLMEndpoint,
)

class StructuredAgent[StructuredOutputT: BaseModel](Protocol):
    """Typed agent capability consumed by domain subsystems."""

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> StructuredOutputT: ...


class LangChainStructuredAgent[StructuredOutputT: BaseModel]:
    """Invoke one strict schema through LangChain with endpoint failover."""

    def __init__(
        self,
        schema: type[StructuredOutputT],
        *,
        endpoints: tuple[LangChainLLMEndpoint, ...],
        project_root: Path | None = None,
        component: AgentEndpointComponent,
    ) -> None:
        self._schema = schema
        self._project_root = project_root
        self._component: AgentEndpointComponent = component
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
            return require_structured_response(
                result,
                self._schema,
            )

        return invoke_agent_endpoint(
            self._endpoints,
            complete,
            project_root=self._project_root,
            component=self._component,
        )


def require_structured_response[StructuredOutputT: BaseModel](
    result: object,
    schema: type[StructuredOutputT],
) -> StructuredOutputT:
    """Return the exact framework structured response or reject the state."""
    if not isinstance(result, dict):
        raise AgentProtocolError(
            "LangChain agent returned invalid state: "
            f"{type(result).__name__}"
        )
    state = cast(dict[str, object], result)
    if "structured_response" not in state:
        raise AgentProtocolError(
            "LangChain agent state is missing structured_response"
        )
    structured = state["structured_response"]
    if not isinstance(structured, schema):
        raise AgentInvalidOutputError(
            "LangChain agent returned invalid structured_response: "
            f"{type(structured).__name__}"
        )
    return structured


def default_structured_agent[StructuredOutputT: BaseModel](
    schema: type[StructuredOutputT],
    *,
    project_root: Path | None = None,
    component: AgentEndpointComponent,
    endpoints: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> StructuredAgent[StructuredOutputT]:
    """Build the framework-native runner from an explicit endpoint set."""
    return LangChainStructuredAgent(
        schema,
        endpoints=endpoints or (),
        project_root=project_root,
        component=component,
    )
