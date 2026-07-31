"""Application-owned chat-thread persistence composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nuself.agent.chat.thread import ThreadStore

if TYPE_CHECKING:
    from nuself.application.composition import ApplicationGraph


def compose_thread_store(application: "ApplicationGraph") -> ThreadStore:
    """Build thread persistence from one authority-owned graph."""

    return ThreadStore(
        application.paths,
        backend=application.backend,
    )
