"""Neutral component and severity types shared by audit infrastructure."""

from __future__ import annotations

from typing import Literal

LogLevel = Literal["debug", "info", "warning", "error"]
LogComponent = Literal[
    "daemon",
    "chat",
    "memory",
    "persona",
    "outbox",
    "reflection",
    "reasoning",
    "storage",
]

LOG_COMPONENTS: tuple[LogComponent, ...] = (
    "daemon",
    "chat",
    "memory",
    "persona",
    "outbox",
    "reflection",
    "reasoning",
    "storage",
)
