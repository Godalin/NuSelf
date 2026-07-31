"""Consumer-owned ports for reflection promotion."""

from __future__ import annotations

from typing import Protocol

from nuself.reason.domain import ReasoningThread


class ReasonThreadStarter(Protocol):
    """Start the one reason thread produced by reflection promotion."""

    def start_thread(
        self,
        topic: str,
        *,
        working_summary: str = "",
        evidence_refs: tuple[str, ...] = (),
    ) -> ReasoningThread: ...


class ReflectionPromotionRecorder(Protocol):
    """Record the provenance edge created by reflection promotion."""

    def record_reflection_promoted(
        self,
        *,
        reflection_id: str,
        reflection_title: str,
        thread: ReasoningThread,
        metadata: dict[str, object] | None = None,
    ) -> object: ...
