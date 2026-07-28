from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nuself.logs import LogComponent, write_log_event
from nuself.runtime.observability import run_observed_best_effort
from typing import cast


def audit_log(component: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            run_observed_best_effort(
                lambda: write_log_event(
                    cast(LogComponent, component),
                    "service_tool_called",
                    f"Tool called: {fn.__name__}",
                    metadata={"tool": fn.__name__},
                ),
                component=cast(LogComponent, component),
                event="audit_log_failed",
                message=f"Could not audit tool call: {fn.__name__}",
                metadata={"tool": fn.__name__},
            )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
