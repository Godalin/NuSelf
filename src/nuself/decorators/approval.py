from __future__ import annotations

import getpass
import json
from functools import wraps
from typing import Any, Callable

from nuself.logs import LogComponent
from nuself.decorators.approval_audit import (
    write_approval_decided,
    write_approval_prompted,
)


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
            write_approval_prompted(
                component,
                tool=fn.__name__,
                summary=summary,
            )
            from nuself.tui.render import render_approval_prompt

            prompt = render_approval_prompt(
                component,
                summary,
                tool=fn.__name__,
            )
            print(prompt, flush=True)
            # Capital N signals the safe default: anything but an explicit yes
            # cancels. EOF is the one input condition that represents an
            # unavailable affirmative decision rather than an implementation
            # failure.
            print("approve? [y/N] ", end="", flush=True)
            try:
                resp = input()
            except EOFError:
                write_approval_decided(
                    component,
                    tool=fn.__name__,
                    approved=False,
                    approver=None,
                    input_kind="eof",
                )
                return json.dumps(
                    {
                        "approved": False,
                        "component": component,
                        "result": None,
                    }
                )
            if resp.strip().lower() in {"y", "yes"}:
                approver = getpass.getuser()
                write_approval_decided(
                    component,
                    tool=fn.__name__,
                    approved=True,
                    approver=approver,
                    input_kind="affirmative",
                )
                result = fn(*args, **kwargs)
                # Return a structured JSON string that preserves the underlying result
                return json.dumps({"approved": True, "component": component, "approver": approver, "result": result})
            # Cancellation also returns a structured JSON string indicating no approval
            write_approval_decided(
                component,
                tool=fn.__name__,
                approved=False,
                approver=None,
                input_kind="declined",
            )
            return json.dumps({"approved": False, "component": component, "result": None})

        return wrapper

    return decorator
