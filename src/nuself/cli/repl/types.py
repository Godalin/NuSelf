"""Typed results shared by REPL orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from nuself.runtime.feature.protocol import ToolEffectRequest


@dataclass(frozen=True)
class InteractiveChatResult:
    code: int
    reply: str | None = None
    retryable: bool = False
    error: str | None = None
    failure_phase: str | None = None
    request_id: str | None = None
    request_may_have_completed: bool = False
    tool_effect_request: ToolEffectRequest | None = None
    after_reply: Callable[[], None] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
