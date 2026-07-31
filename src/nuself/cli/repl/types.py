"""Typed results shared by REPL orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InteractiveChatResult:
    code: int
    reply: str | None = None
    retryable: bool = False
    error: str | None = None
    failure_phase: str | None = None
    request_id: str | None = None
    request_may_have_completed: bool = False
