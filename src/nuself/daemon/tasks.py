"""Closed task names for the single daemon scheduler."""

from typing import Literal

DaemonTaskKind = Literal[
    "memory.scan",
    "memory.curate",
    "chat.turn",
    "conversation.compress",
    "reflection.check",
    "reason.check",
    "notification.deliver",
    "reason.export",
]
PeriodicTaskKind = Literal[
    "memory.scan",
    "reflection.check",
    "reason.check",
    "notification.deliver",
]

DAEMON_TASK_KINDS: tuple[DaemonTaskKind, ...] = (
    "memory.scan",
    "memory.curate",
    "chat.turn",
    "conversation.compress",
    "reflection.check",
    "reason.check",
    "notification.deliver",
    "reason.export",
)
