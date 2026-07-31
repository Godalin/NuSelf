"""LangChain adapter for orthogonally decorated feature functions."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from langchain_core.tools import StructuredTool

from nuself.runtime.feature_execution import FeatureExecutor
from nuself.runtime.features import require_tool_spec

P = ParamSpec("P")
R = TypeVar("R")


def materialize_tool(
    function: Callable[P, R],
    *,
    executor: FeatureExecutor,
) -> StructuredTool:
    """Materialize one declared function through LangChain's native API."""

    spec = require_tool_spec(function)
    assert spec.tool is not None
    assert spec.component is not None
    assert spec.effect is not None

    @wraps(function)
    def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
        return executor.invoke(function, *args, **kwargs)

    name = spec.tool.name or function.__name__
    description = spec.tool.description or function.__doc__
    tags = ("readonly" if spec.effect == "readonly" else "write",)
    metadata = {
        "service_component": spec.component,
        "effect": spec.effect,
        "confirmation_required": spec.confirmation is not None,
    }
    factory = cast(Callable[..., StructuredTool], StructuredTool.from_function)
    return factory(
        func=invoke,
        name=name,
        description=description,
        tags=tags,
        metadata=metadata,
    )
