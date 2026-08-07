"""LangChain adapter for orthogonally decorated feature functions."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import cast

from langchain_core.tools import StructuredTool

from nuself.runtime.feature.execution import FeatureExecutor
from nuself.runtime.feature.policy import require_tool_spec

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
        return executor.invoke(function, *args, **kwargs)

    name = spec.tool.name or function.__name__
    description = spec.tool.description or function.__doc__
    tags = ("readonly" if spec.execution == "readonly" else "write",)
    metadata = {
        "service_component": spec.component,
        "execution": spec.execution,
        "compact": spec.compact is not None,
    }
    factory = cast(Callable[..., StructuredTool], StructuredTool.from_function)
    return factory(
        func=invoke,
        name=name,
        description=description,
        tags=tags,
        metadata=metadata,
        handle_tool_error=True,
    )
