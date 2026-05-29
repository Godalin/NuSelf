from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nuself.logs import write_log_event, LogComponent
from typing import cast


def audit_log(component: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                write_log_event(cast(LogComponent, component), "service_tool_called", f"Tool called: {fn.__name__}", metadata={"tool": fn.__name__})
            except Exception:
                pass
            return fn(*args, **kwargs)

        return wrapper

    return decorator
