"""Closed task names for the single daemon scheduler."""

from typing import Literal, get_args

from nuself.daemon.scheduler import DaemonTask
from nuself.runtime.context import RuntimeContext

DaemonTaskKind = Literal[
    "memory.scan",
    "memory.curate",
    "conversation.scan",
    "chat.turn",
    "conversation.compress",
    "reflection.check",
    "reason.check",
    "notification.deliver",
    "reason.export",
]
PeriodicTaskKind = Literal[
    "memory.scan",
    "conversation.scan",
    "reflection.check",
    "reason.check",
    "notification.deliver",
]

DAEMON_TASK_KINDS: tuple[str, ...] = get_args(DaemonTaskKind)


def daemon_task(
    kind: DaemonTaskKind,
    identity: str,
    resource: str,
    *,
    payload: object = None,
    priority: int = 100,
    context: RuntimeContext | None = None,
) -> DaemonTask:
    """Construct a production task through the closed kind boundary."""

    if context is None:
        return DaemonTask(
            kind,
            identity,
            resource,
            payload=payload,
            priority=priority,
        )
    return DaemonTask(
        kind,
        identity,
        resource,
        payload=payload,
        priority=priority,
        context=context,
    )
