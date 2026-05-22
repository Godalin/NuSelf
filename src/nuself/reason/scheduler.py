"""Background reason scheduler — advances active reasoning threads via LLM."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nuself.llm import LangChainLLMEndpoint
from nuself.memory.query import MemoryQueryService
from nuself.reason.advancer import ReasonAdvancer
from nuself.reason.domain import ACTIVE_STATUSES, ReasoningThread
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository


class ReasonScheduler:
    """Decides which active reasoning thread to advance next and calls ReasonAdvancer."""

    def __init__(
        self,
        project_root: Path | None = None,
        advancer: ReasonAdvancer | None = None,
        service: ReasonService | None = None,
        interval_seconds: int = 600,
        *,
        memory_query_service: MemoryQueryService | None = None,
        reflection_repository: ReflectionRepository | None = None,
        readonly_tools: Sequence[Any] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
        self._advancer = advancer
        self._service = service or ReasonService(project_root)
        self._repository = ReasonRepository(project_root)
        self._interval_seconds = interval_seconds

        if advancer is None and project_root is not None:
            from nuself.llm import default_llm
            llm = default_llm(project_root)
            self._advancer = ReasonAdvancer(
                llm,
                project_root=project_root,
                memory_query_service=memory_query_service,
                reflection_repository=reflection_repository,
                readonly_tools=readonly_tools,
                langchain_models=langchain_models,
            )

    def run_once(self) -> None:
        """Advance exactly one thread if any active thread is not on cooldown."""
        if self._advancer is None:
            return

        threads = self._service.list_threads(status=None)
        active = [t for t in threads if t.status in ACTIVE_STATUSES]

        now = datetime.now(UTC)
        candidate: ReasoningThread | None = None

        for t in active:
            if t.skip_next_advance_until:
                try:
                    cooldown_end = datetime.fromisoformat(t.skip_next_advance_until)
                    if now < cooldown_end:
                        continue
                except ValueError:
                    pass
            candidate = t
            break

        if candidate is None:
            return

        step = self._advancer.advance(candidate)
        if step is None:
            return

        updated = self._service.advance_thread(candidate.id, step=step)
        cooldown_end = (datetime.now(UTC) + timedelta(seconds=self._interval_seconds)).isoformat()
        cooled = ReasoningThread(
            id=updated.id,
            question=updated.question,
            status=updated.status,
            working_summary=updated.working_summary,
            hypotheses=list(updated.hypotheses),
            open_questions=list(updated.open_questions),
            evidence_refs=list(updated.evidence_refs),
            priority=updated.priority,
            last_advanced_at=updated.last_advanced_at,
            next_review_after=updated.next_review_after,
            skip_next_advance_until=cooldown_end,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )
        self._repository.save_thread(cooled)

        from nuself.logs import write_log_event
        write_log_event(
            "reasoning",
            "scheduler_advance",
            f"Background advance for thread {candidate.id}: {step.kind}",
            project_root=self._project_root,
            status="completed",
            metadata={"thread_id": candidate.id, "step_kind": step.kind, "step_id": step.id},
        )
