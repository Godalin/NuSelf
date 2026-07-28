from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nuself.logs import LogComponent
from nuself.runtime.observability import write_observed_log_event


def audit_log(
    component: LogComponent,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            write_observed_log_event(
                component,
                "service_tool_called",
                f"Tool called: {fn.__name__}",
                metadata={"tool": fn.__name__},
                failure_event="audit_log_failed",
                failure_message=f"Could not audit tool call: {fn.__name__}",
                failure_metadata={"tool": fn.__name__},
            )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
