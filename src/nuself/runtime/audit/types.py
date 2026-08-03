"""Neutral component and severity types shared by audit infrastructure."""

from __future__ import annotations

from typing import Literal

type LogLevel = Literal["debug", "info", "warning", "error"]
type LogComponent = Literal[
    "daemon",
    "chat",
    "memory",
    "persona",
    "inbox",
    "delivery",
    "reflection",
    "reasoning",
    "storage",
]

LOG_COMPONENTS: tuple[LogComponent, ...] = (
    "daemon",
    "chat",
    "memory",
    "persona",
    "inbox",
    "delivery",
    "reflection",
    "reasoning",
    "storage",
)
