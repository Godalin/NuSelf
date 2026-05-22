"""Reason subsystem service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nuself.logs import write_log_event
from nuself.reason.domain import ReasoningStep, ReasoningThread, ReasonStatus
from nuself.reason.repository import ReasonRepository
from nuself.store import ScopedWorkspace, SqliteStore
from nuself.trace.service import TraceRecorder
from nuself.workspace import PrivateWorkspacePaths, PrivateWorkspaceStore

MAX_ACTIVE_THREADS = 5


class ReasonService:
    """User-intent operations and state transitions for reasoning threads."""

    def __init__(
        self,
        project_root: Path | None = None,
        repository: ReasonRepository | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self._project_root = project_root
        self._repository = repository or ReasonRepository(project_root)
        repo_root = self._repository.project_root
        effective_root = repo_root if repo_root is not None else project_root
        self._workspace_store = workspace_store or PrivateWorkspaceStore(effective_root, scope="reason")
        self._trace_recorder = trace_recorder if trace_recorder is not None else (
            TraceRecorder(effective_root) if effective_root is not None else None
        )
        self._workspace_cache: dict[str, ScopedWorkspace] = {}

    # ── Read ───────────────────────────────────────────────────────

    def list_threads(self, status: str | None = None) -> list[ReasoningThread]:
        return self._repository.list_threads(status=status)

    def show_thread(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        return self._repository.resolve_thread(id_or_index, by_index=by_index)

    def list_steps(self, thread_id: str) -> list[ReasoningStep]:
        return self._repository.list_steps(thread_id)

    def workspace_paths(self, thread_id: str) -> PrivateWorkspacePaths:
        self._repository.get_thread(thread_id)
        return self._workspace_store.paths(thread_id)

    def workspace(self, thread_id: str) -> ScopedWorkspace:
        """Return a thread-scoped workspace for the given thread."""
        cached = self._workspace_cache.get(thread_id)
        if cached is not None:
            return cached
        ws = self._workspace_store.ensure(thread_id)
        store = SqliteStore(ws.database)
        w = ScopedWorkspace(store, (thread_id,))
        self._workspace_cache[thread_id] = w
        return w

    # ── Write ──────────────────────────────────────────────────────

    def start_thread(
        self,
        question: str,
        *,
        working_summary: str = "",
        evidence_refs: tuple[str, ...] = (),
        source_trace_ids: tuple[str, ...] = (),
        priority: str = "normal",
    ) -> ReasoningThread:
        active = self._repository.list_threads(status="active")
        if len(active) >= MAX_ACTIVE_THREADS:
            active_names = "\n".join(f"  - {t.id}: {t.question[:60]}" for t in active)
            raise RuntimeError(
                f"Cannot start new thread: already {len(active)} active threads "
                f"(max {MAX_ACTIVE_THREADS}). Please pause, resolve, or archive one first.\n"
                f"Active threads:\n{active_names}"
            )

        thread = ReasoningThread(
            question=question.strip(),
            working_summary=working_summary.strip(),
            priority="normal" if priority not in ("normal", "high") else priority,  # type: ignore[arg-type]
            evidence_refs=list(evidence_refs),
        )
        saved = self._repository.save_thread(thread)
        workspace = self._workspace_store.ensure(thread.id)
        if self._trace_recorder is not None:
            self._trace_recorder.record_reason_thread_created(
                thread=saved,
                source_trace_ids=list(source_trace_ids),
                metadata={"workspace": str(workspace.root)},
            )

        write_log_event(
            "reasoning",
            "thread_started",
            f"Started reasoning thread: {thread.question[:80]}",
            project_root=self._project_root,
            status="created",
            metadata={"thread_id": thread.id, "question": thread.question, "workspace": str(workspace.root)},
        )
        return saved

    def advance_thread(
        self,
        id_or_index: str,
        *,
        by_index: bool = False,
        step: ReasoningStep | None = None,
    ) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)

        if thread.status != "active":
            raise RuntimeError(f"Cannot advance thread {thread.id}: status is '{thread.status}', expected 'active'")

        write_log_event(
            "reasoning",
            "advance_started",
            f"Advancing reasoning thread: {thread.question[:80]}",
            project_root=self._project_root,
            status="started",
            metadata={"thread_id": thread.id},
        )

        if step is not None:
            self._repository.save_step(step)
        else:
            step = ReasoningStep(
                thread_id=thread.id,
                kind="progress",
                summary=f"Manual advance requested for: {thread.question[:80]}",
                delta="Manual advance placeholder — LLM integration deferred.",
                evidence_refs=list(thread.evidence_refs),
            )
            self._repository.save_step(step)

        now = datetime.now(UTC).isoformat()
        updated = ReasoningThread(
            id=thread.id,
            question=thread.question,
            status=thread.status,
            working_summary=thread.working_summary,
            hypotheses=list(thread.hypotheses),
            open_questions=list(thread.open_questions),
            evidence_refs=list(thread.evidence_refs),
            priority=thread.priority,
            last_advanced_at=now,
            next_review_after=thread.next_review_after,
            created_at=thread.created_at,
            updated_at=now,
        )
        self._repository.save_thread(updated)
        if self._trace_recorder is not None:
            self._trace_recorder.record_reason_step(thread=updated, step=step)

        write_log_event(
            "reasoning",
            "advance_completed",
            f"Advance completed for thread: {thread.question[:80]}",
            project_root=self._project_root,
            status="completed",
            metadata={"thread_id": thread.id, "step_id": step.id, "step_kind": step.kind},
        )
        return updated

    def pause_thread(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)
        return self._transition(thread, "paused")

    def resume_thread(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)
        return self._transition(thread, "active")

    def resolve_thread(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)
        return self._transition(thread, "resolved")

    def archive_thread(self, id_or_index: str, *, by_index: bool = False) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)
        return self._transition(thread, "archived")

    def delete_thread(self, id_or_index: str, *, by_index: bool = False) -> str:
        thread = self._repository.resolve_thread(id_or_index, by_index=by_index)

        write_log_event(
            "reasoning",
            "thread_deleted",
            f"Deleted reasoning thread: {thread.question[:80]}",
            project_root=self._project_root,
            status="deleted",
            metadata={"thread_id": thread.id, "question": thread.question},
        )

        import shutil
        ws = self._workspace_store.paths(thread.id)
        if ws.root.exists():
            shutil.rmtree(ws.root)

        self._repository.delete_thread(thread.id)
        return thread.id

    # ── Internal ───────────────────────────────────────────────────

    def _transition(self, thread: ReasoningThread, new_status: ReasonStatus) -> ReasoningThread:
        allowed: dict[ReasonStatus, tuple[ReasonStatus, ...]] = {
            "active": ("paused", "resolved", "archived"),
            "paused": ("active", "resolved", "archived"),
            "resolved": ("archived",),
            "archived": (),
        }
        if thread.status not in allowed or new_status not in allowed[thread.status]:
            raise RuntimeError(f"Cannot transition thread {thread.id} from '{thread.status}' to '{new_status}'")

        updated = thread.with_status(new_status)
        self._repository.save_thread(updated)

        event_name = "thread_status_changed"
        write_log_event(
            "reasoning",
            event_name,
            f"Thread {thread.id} status changed: {thread.status} -> {new_status}",
            project_root=self._project_root,
            status="updated",
            metadata={"thread_id": thread.id, "from_status": thread.status, "to_status": new_status},
        )
        return updated
