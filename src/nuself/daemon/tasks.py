"""Closed task names for the single daemon scheduler."""

from typing import Literal, get_args

from nuself.daemon.scheduler import DaemonTask
from nuself.runtime.context import RuntimeContext, current_runtime_context

# This assignment intentionally remains an evaluated typing expression:
# ``get_args`` below uses it as the runtime task catalog.
DaemonTaskKind = Literal[
    "memory.scan",
    "memory.curate",
    "conversation.scan",
    "chat.turn",
    "conversation.compress",
    "reflection.check",
    "reason.check",
    "delivery.run",
    "reason.export",
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

    return DaemonTask(
        kind,
        identity,
        resource,
        payload=payload,
        priority=priority,
        context=context if context is not None else current_runtime_context(),
    )
