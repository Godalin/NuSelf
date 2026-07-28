"""Shared in-process prompt message values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

ChatRole: TypeAlias = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """One temporary prompt message shared by agent-facing services."""

    role: ChatRole
    content: str
