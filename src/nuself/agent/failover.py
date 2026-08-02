"""Shared endpoint invocation for framework-native agent capabilities."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import time
from math import isfinite

from nuself.agent.errors import AgentModelUnavailableError
from nuself.agent.endpoint_audit import (
    AgentEndpointComponent,
    report_agent_endpoint_failure,
)
from nuself.llm import (
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
    redact_llm_error,
)


type FailurePredicate = Callable[[Exception], bool]
type RetryObserver = Callable[[LangChainLLMEndpoint, Exception], None]
_AGENT_IMPLEMENTATION_ERRORS = (
    AssertionError,
    AttributeError,
    ImportError,
    LookupError,
    MemoryError,
    NameError,
    NotImplementedError,
    RecursionError,
    SyntaxError,
    SystemError,
    TypeError,
)


def is_recoverable_agent_failure(exc: Exception) -> bool:
    """Return whether an agent failure may enter a domain fallback policy."""

    return not isinstance(exc, _AGENT_IMPLEMENTATION_ERRORS)


def invoke_agent_endpoint[ResultT](
    endpoints: tuple[LangChainLLMEndpoint, ...],
    operation: Callable[[LangChainLLMEndpoint], ResultT],
    *,
    project_root: Path | None,
    component: AgentEndpointComponent,
    attempts_per_endpoint: int = 1,
    retry_if: FailurePredicate | None = None,
    failover_if: FailurePredicate | None = None,
    on_retry: RetryObserver | None = None,
    retry_delay_seconds: float = 0.0,
) -> ResultT:
    """Invoke one capability with shared retry and ordered endpoint failover."""
    if not endpoints:
        raise AgentModelUnavailableError("no configured LangChain model")
    if attempts_per_endpoint < 1:
        raise ValueError("attempts_per_endpoint must be at least 1")
    if (
        isinstance(retry_delay_seconds, bool)
        or not isfinite(retry_delay_seconds)
        or retry_delay_seconds < 0
    ):
        raise ValueError(
            "retry_delay_seconds must be finite and non-negative"
        )
    should_failover = failover_if or is_endpoint_availability_error

    last_error: Exception | None = None
    for position, endpoint in enumerate(endpoints):
        for attempt in range(attempts_per_endpoint):
            try:
                result = operation(endpoint)
            except Exception as exc:
                last_error = exc
                has_retry = attempt + 1 < attempts_per_endpoint
                if (
                    has_retry
                    and retry_if is not None
                    and retry_if(exc)
                ):
                    if on_retry is not None:
                        on_retry(endpoint, exc)
                    if retry_delay_seconds:
                        time.sleep(retry_delay_seconds)
                    continue
                if not should_failover(exc):
                    raise
                has_next = position + 1 < len(endpoints)
                report_agent_endpoint_failure(
                    exc,
                    endpoint_index=endpoint.index,
                    model=endpoint.settings.model,
                    has_next=has_next,
                    project_root=project_root,
                    component=component,
                )
                break
            else:
                record_llm_endpoint_success(
                    project_root,
                    endpoint.index,
                )
                return result

    assert last_error is not None
    raise AgentModelUnavailableError(
        "all configured LLM endpoints failed: "
        f"{redact_llm_error(last_error)}"
    ) from last_error
