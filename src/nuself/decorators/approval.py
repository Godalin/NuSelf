from __future__ import annotations

import getpass
import json
from functools import wraps
from typing import Any, Callable

from nuself.logs import LogComponent, write_log_event


def approval_required(
    component: LogComponent,
    summary_builder: Callable[[tuple[Any, ...], dict[str, Any]], str] | None = None,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            if summary_builder is not None:
                summary = summary_builder(args, kwargs)
            else:
                summary = f"{fn.__name__}({', '.join(map(str, args))}{', ' if kwargs else ''}{', '.join(f'{k}={v}' for k, v in kwargs.items())})"
            # Always prompt the user synchronously and execute immediately on confirmation.
            # Record the event first, then render a theme-consistent banner so
            # interactive users see the pending action before the question.
            write_log_event(
                component,
                "approval_prompted",
                summary,
                metadata={"tool": fn.__name__, "summary": summary},
            )
            from nuself.tui.render import render_approval_prompt

            try:
                print(render_approval_prompt(component, summary, tool=fn.__name__), flush=True)
                # Capital N signals the safe default: anything but an explicit yes cancels.
                print("approve? [y/N] ", end="", flush=True)
                resp = input()
            except Exception:
                resp = "n"
            if resp.strip().lower() in {"y", "yes"}:
                result = fn(*args, **kwargs)
                write_log_event(component, "service_tool_executed", f"Tool executed interactively: {fn.__name__}", metadata={"tool": fn.__name__})
                # Also log an explicit approval record with the approver identity.
                approver = getpass.getuser()
                write_log_event(component, "service_tool_approved", f"{component} approved by {approver}", metadata={"tool": fn.__name__, "approver": approver})
                # Return a structured JSON string that preserves the underlying result
                return json.dumps({"approved": True, "component": component, "approver": approver, "result": result})
            # Cancellation also returns a structured JSON string indicating no approval
            return json.dumps({"approved": False, "component": component, "result": None})

        return wrapper

    return decorator
