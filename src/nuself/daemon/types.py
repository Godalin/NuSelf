"""Shared daemon runtime state records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerHealth:
    name: str
    alive: bool = False
    last_success_at: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
