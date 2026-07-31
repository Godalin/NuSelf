"""Background reason scheduler — advances active reasoning threads via LLM."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.clock import utc_now
from nuself.config import runtime_paths
from nuself.llm import LangChainLLMEndpoint
from nuself.reason.advancer import (
    ReasonAdvancer,
    default_reason_advancer,
)
from nuself.reason.audit import report_reason_failure, write_reason_audit
from nuself.reason.domain import ReasoningThread
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.runtime.context import runtime_context
from nuself.storage import get_default_backend


class ReasonScheduler:
    """Decides which active reasoning thread to advance next and calls ReasonAdvancer."""

    def __init__(
        self,
        project_root: Path | None = None,
        advancer: ReasonAdvancer | None = None,
        service: ReasonService | None = None,
        interval_seconds: int = 600,
        *,
        readonly_tools: Sequence[BaseTool] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
        repository: ReasonRepository | None = None,
    ) -> None:
        self._project_root = project_root
        self._advancer = advancer
        self._service = service or ReasonService(project_root)
        self._repository = repository or ReasonRepository(
            runtime_paths(project_root),
            backend=get_default_backend(project_root),
        )
        self._interval_seconds = interval_seconds

        if advancer is None and project_root is not None:
            self._advancer = default_reason_advancer(
                project_root=project_root,
                readonly_tools=readonly_tools,
                langchain_models=langchain_models,
            )

    def run_once(self) -> None:
        """Advance exactly one thread if any active thread is not on cooldown."""
        if self._advancer is None:
            return

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
            thread_id=candidate.id,
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
        cooled = ReasoningThread(
            id=thread.id,
            topic=thread.topic,
            status=thread.status,
            working_summary=thread.working_summary,
            evidence_refs=list(thread.evidence_refs),
            priority=thread.priority,
            last_advanced_at=thread.last_advanced_at,
            next_review_after=thread.next_review_after,
            skip_next_advance_until=cooldown_end,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            active_items_data=thread.active_items_data,
            pending_items_data=thread.pending_items_data,
            next_steps_data=thread.next_steps_data,
            mandates_data=thread.mandates_data,
            reasoning_prompt=thread.reasoning_prompt,
        )
        self._repository.save_thread(cooled)
