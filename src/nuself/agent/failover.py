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


def invoke_agent_endpoint(
    endpoints: tuple[LangChainLLMEndpoint, ...],
    operation: Callable[[LangChainLLMEndpoint], ResultT],
    *,
    project_root: Path | None,
    component: LogComponent,
) -> ResultT:
    """Invoke one capability with shared ordered endpoint failover."""
    if not endpoints:
        raise RuntimeError("no configured LangChain model")

    last_error: Exception | None = None
    for position, endpoint in enumerate(endpoints):
        try:
            result = operation(endpoint)
        except Exception as exc:
            if not is_endpoint_availability_error(str(exc)):
                raise
            last_error = exc
            has_next = position + 1 < len(endpoints)
            _report_endpoint_failure(
                exc,
                endpoint=endpoint,
                has_next=has_next,
                project_root=project_root,
                component=component,
            )
            continue
        record_llm_endpoint_success(project_root, endpoint.index)
        return result

    assert last_error is not None
    raise RuntimeError(
        "all configured LLM endpoints failed: "
        f"{redact_llm_error(str(last_error))}"
    ) from last_error


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
