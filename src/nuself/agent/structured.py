"""Framework-native structured-output invocation for agent subsystems."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
    redact_llm_error,
)
from nuself.logs import LogComponent
from nuself.runtime.observability import report_observed_failure

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
        self._agents = tuple(
            (
                endpoint,
                create_agent(
                    model=endpoint.model,
                    tools=[],
                    response_format=ToolStrategy(schema),
                ),
            )
            for endpoint in endpoints
        )

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> StructuredOutputT:
        if not self._agents:
            raise RuntimeError("no configured LangChain model")
        last_error: Exception | None = None
        for position, (endpoint, agent) in enumerate(self._agents):
            try:
                result: object = agent.invoke({"messages": list(messages)})
                structured = self._structured_response(result)
            except Exception as exc:
                if not is_endpoint_availability_error(str(exc)):
                    raise
                last_error = exc
                self._report_endpoint_failure(
                    exc,
                    endpoint=endpoint,
                    has_next=position + 1 < len(self._agents),
                )
                continue
            record_llm_endpoint_success(self._project_root, endpoint.index)
            return structured
        assert last_error is not None
        raise RuntimeError(
            "all configured LLM endpoints failed: "
            f"{redact_llm_error(str(last_error))}"
        ) from last_error

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

    def _report_endpoint_failure(
        self,
        exc: Exception,
        *,
        endpoint: LangChainLLMEndpoint,
        has_next: bool,
    ) -> None:
        report_observed_failure(
            RuntimeError(redact_llm_error(str(exc))),
            component=self._component,
            event=(
                "llm_endpoint_failed_over"
                if has_next
                else "llm_endpoint_unavailable"
            ),
            message=(
                "LLM endpoint failed; trying next configured endpoint"
                if has_next
                else "LLM endpoint failed and no fallback endpoint remains"
            ),
            project_root=self._project_root,
            level="warning",
            status="failed_over" if has_next else "exhausted",
            metadata={
                "endpoint_index": endpoint.index,
                "base_url": endpoint.settings.base_url,
                "model": endpoint.settings.model,
            },
        )


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
