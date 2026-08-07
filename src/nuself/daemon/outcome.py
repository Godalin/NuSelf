"""Closed daemon Chat execution outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.agent.chat.types import ChatResult
from nuself.runtime.feature.protocol import ToolEffectRequest


@dataclass(frozen=True)
class ChatCompleted:
    """A daemon Chat task completed with a domain result."""

    result: ChatResult


@dataclass(frozen=True)
class ChatSuspended:
    """A daemon Chat task paused for one frontend Tool effect."""

    request: ToolEffectRequest


type ChatOutcome = ChatCompleted | ChatSuspended


__all__ = ["ChatCompleted", "ChatOutcome", "ChatSuspended"]
