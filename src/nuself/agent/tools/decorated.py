"""LangChain adapter for orthogonally decorated feature functions."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import cast

from langchain_core.tools import StructuredTool

from nuself.runtime.feature.execution import (
    FeatureExecutor,
    ToolEffectDeclined,
)
from nuself.runtime.feature.policy import (
    ApprovalEffectPolicy,
    AuditEffectPolicy,
    ObservationEffectPolicy,
    require_tool_spec,
)

def materialize_tool[**P](
    function: Callable[P, str],
    *,
    executor: FeatureExecutor,
) -> StructuredTool:
    """Materialize one declared function through LangChain's native API."""

    spec = require_tool_spec(function)
    assert spec.tool is not None
    assert spec.component is not None
    assert spec.execution is not None

    @wraps(function)
    def invoke(*args: P.args, **kwargs: P.kwargs) -> str:
        try:
            return executor.invoke(function, *args, **kwargs)
        except ToolEffectDeclined:
            return "Action was not approved; no changes were made."

    name = spec.tool.name or function.__name__
    description = spec.tool.description or function.__doc__
    tags = ("readonly" if spec.execution == "readonly" else "write",)
    metadata = {
        "service_component": spec.component,
        "execution": spec.execution,
        "confirmation_required": any(
            isinstance(effect, ApprovalEffectPolicy)
            for effect in spec.effects
        ),
        "observed": any(
            isinstance(effect, ObservationEffectPolicy)
            for effect in spec.effects
        ),
        "compact": spec.compact is not None,
        "audit_event": (
            next(
                (
                    effect.event
                    for effect in spec.effects
                    if isinstance(effect, AuditEffectPolicy)
                ),
                None,
            )
        ),
    }
    factory = cast(Callable[..., StructuredTool], StructuredTool.from_function)
    return factory(
        func=invoke,
        name=name,
        description=description,
        tags=tags,
        metadata=metadata,
        handle_tool_error=any(
            isinstance(effect, ApprovalEffectPolicy)
            for effect in spec.effects
        ),
    )
