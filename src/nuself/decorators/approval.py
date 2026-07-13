from __future__ import annotations

import getpass
import json
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, cast
from uuid import uuid4

from nuself.logs import LogComponent, write_log_event


class ApprovalManager:
    _instance: Optional["ApprovalManager"] = None

    def __init__(self) -> None:
        self._pending: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "ApprovalManager":
        if cls._instance is None:
            cls._instance = ApprovalManager()
        return cls._instance

    def create_proposal(self, component: str, summary: str, *, callable: Callable[..., str], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        pid = uuid4().hex[:12]
        self._pending[pid] = {"component": component, "summary": summary, "callable": callable, "args": args, "kwargs": kwargs}
        write_log_event(cast(LogComponent, component), "proposal_created", summary, metadata={"proposal_id": pid, "summary": summary})
        return pid

    def list_pending(self) -> List[Dict[str, Any]]:
        return [dict(id=pid, component=v["component"], summary=v["summary"]) for pid, v in self._pending.items()]

    def approve(self, proposal_id: str, approver: str | None = None) -> Dict[str, Any]:
        """Approve a pending proposal, execute the original callable, and return a structured result.

        Returns a dict containing approval metadata and the underlying callable's result.
        """
        data = self._pending.get(proposal_id)
        if data is None:
            raise KeyError(f"proposal not found: {proposal_id}")
        func = data["callable"]
        args = data["args"]
        kwargs = data["kwargs"]
        # Execute the original action and capture its result.
        result = func(*args, **kwargs)
        approved_at = datetime.now(timezone.utc).isoformat()
        write_log_event(
            cast(LogComponent, data["component"]),
            "proposal_approved",
            f"Proposal approved: {proposal_id}",
            metadata={"proposal_id": proposal_id, "approver": approver, "approved_at": approved_at},
        )
        # Remove the pending proposal and return structured outcome.
        del self._pending[proposal_id]
        return {
            "status": "approved",
            "proposal_id": proposal_id,
            "component": data["component"],
            "summary": data["summary"],
            "approver": approver,
            "approved_at": approved_at,
            "result": result,
        }

    def reset(self) -> None:
        """Reset pending proposals (test helper)."""
        self._pending = {}


def approval_required(
    component: str,
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
                cast(LogComponent, component),
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
                write_log_event(cast(LogComponent, component), "service_tool_executed", f"Tool executed interactively: {fn.__name__}", metadata={"tool": fn.__name__})
                # Also log an explicit approval record with the approver identity.
                approver = getpass.getuser()
                write_log_event(cast(LogComponent, component), "service_tool_approved", f"{component} approved by {approver}", metadata={"tool": fn.__name__, "approver": approver})
                # Return a structured JSON string that preserves the underlying result
                return json.dumps({"approved": True, "component": component, "approver": approver, "result": result})
            # Cancellation also returns a structured JSON string indicating no approval
            return json.dumps({"approved": False, "component": component, "result": None})

        return wrapper

    return decorator
