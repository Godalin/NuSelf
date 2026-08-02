"""Background reason scheduler — advances active reasoning threads via LLM."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from nuself.clock import utc_now
from nuself.reason.audit import report_reason_failure, write_reason_audit
from nuself.reason.model import ReasoningThread
from nuself.reason.service import ReasonAdvancerProtocol, ReasonService
from nuself.runtime.context import runtime_context


class ReasonScheduler:
    """Decides which active reasoning thread to advance next and calls ReasonAdvancer."""

    def __init__(
        self,
        project_root: Path,
        advancer: ReasonAdvancerProtocol,
        interval_seconds: int = 600,
        *,
        service: ReasonService,
    ) -> None:
        self._project_root = project_root
        self._advancer = advancer
        self._service = service
        self._interval_seconds = interval_seconds

    def run_once(self) -> None:
        """Advance exactly one thread if any active thread is not on cooldown."""
        threads = self._service.list_threads(status=None)
        active = [t for t in threads if t.status == "active"]

        now = utc_now()
        candidate: ReasoningThread | None = None

        for t in active:
            if t.skip_next_advance_until:
                cooldown_end = datetime.fromisoformat(
                    t.skip_next_advance_until
                )
                if now < cooldown_end:
                    continue
            candidate = t
            break

        if candidate is None:
            return

        with runtime_context(
            reason_id=candidate.id,
            source="reason_scheduler",
        ):
            try:
                step = self._advancer.advance(candidate)
            except Exception as exc:
                self._apply_cooldown(candidate)
                report_reason_failure(
                    exc,
                    event="scheduler_advance_failed",
                    project_root=self._project_root,
                    metadata={},
                )
                return
            if step is None:
                self._apply_cooldown(candidate)
                return
            updated = self._service.advance_thread(candidate.id, step=step)
            self._apply_cooldown(updated)
            write_reason_audit(
                "scheduler_advance_completed",
                project_root=self._project_root,
                metadata={"step_kind": step.kind, "step_id": step.id},
            )

    def _apply_cooldown(self, thread: ReasoningThread) -> None:
        cooldown_end = (
            utc_now() + timedelta(seconds=self._interval_seconds)
        ).isoformat()
        self._service.defer_advancement(
            thread.id,
            until=cooldown_end,
        )
