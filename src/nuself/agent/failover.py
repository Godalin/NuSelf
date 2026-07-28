"""Shared endpoint invocation for framework-native agent capabilities."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from nuself.llm import (
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
    redact_llm_error,
)
from nuself.logs import LogComponent
from nuself.runtime.observability import report_observed_failure


ResultT = TypeVar("ResultT")
FailurePredicate = Callable[[Exception], bool]
RetryObserver = Callable[[LangChainLLMEndpoint, Exception], None]
_AGENT_IMPLEMENTATION_ERRORS = (
    AssertionError,
    AttributeError,
    TypeError,
)


def is_recoverable_agent_failure(exc: Exception) -> bool:
    """Return whether an agent failure may enter a domain fallback policy."""

    return not isinstance(exc, _AGENT_IMPLEMENTATION_ERRORS)


def invoke_agent_endpoint(
    endpoints: tuple[LangChainLLMEndpoint, ...],
    operation: Callable[[LangChainLLMEndpoint], ResultT],
    *,
    project_root: Path | None,
    component: LogComponent,
    attempts_per_endpoint: int = 1,
    retry_if: FailurePredicate | None = None,
    failover_if: FailurePredicate | None = None,
    on_retry: RetryObserver | None = None,
) -> ResultT:
    """Invoke one capability with shared retry and ordered endpoint failover."""
    if not endpoints:
        raise RuntimeError("no configured LangChain model")
    if attempts_per_endpoint < 1:
        raise ValueError("attempts_per_endpoint must be at least 1")
    should_failover = failover_if or _is_availability_failure

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
                    continue
                if not should_failover(exc):
                    raise
                has_next = position + 1 < len(endpoints)
                _report_endpoint_failure(
                    exc,
                    endpoint=endpoint,
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
    raise RuntimeError(
        "all configured LLM endpoints failed: "
        f"{redact_llm_error(str(last_error))}"
    ) from last_error


def _is_availability_failure(exc: Exception) -> bool:
    return is_endpoint_availability_error(str(exc))


def _report_endpoint_failure(
    exc: Exception,
    *,
    endpoint: LangChainLLMEndpoint,
    has_next: bool,
    project_root: Path | None,
    component: LogComponent,
) -> None:
    report_observed_failure(
        RuntimeError(redact_llm_error(str(exc))),
        component=component,
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
        project_root=project_root,
        level="warning",
        status="failed_over" if has_next else "exhausted",
        metadata={
            "endpoint_index": endpoint.index,
            "base_url": endpoint.settings.base_url,
            "model": endpoint.settings.model,
        },
    )
