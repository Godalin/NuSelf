"""Shared helpers for memory command modules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself.memory.audit import run_memory_observed
from nuself.trace.service import TraceRecorder


class TraceableMemory(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def body(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def confidence(self) -> float: ...


def record_memory_trace(
    recorder: TraceRecorder,
    project_root: Path | None,
    entry: TraceableMemory,
    action: str,
) -> None:
    run_memory_observed(
        lambda: recorder.record_memory_update(
            memory_id=entry.id,
            title=entry.title,
            summary=entry.body,
            memory_type=entry.type,
            action=action,
            confidence=entry.confidence,
        ),
        event="trace_recording_failed",
        project_root=project_root,
        metadata={"memory_id": entry.id, "action": action},
    )
