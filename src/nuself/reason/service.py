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
_MAX_HYPOTHESES = 10
_MAX_OPEN_QUESTIONS = 10
_MAX_EVIDENCE_REFS = 20


def _pick_working_summary(step: ReasoningStep | None, thread: ReasoningThread) -> str:
    if step is not None and step.summary:
        return step.summary
    return thread.working_summary


def _merge_str_lists(existing: list[str], new_items: list[str], *, max_items: int = 10) -> list[str]:
    seen = set(existing)
    merged = existing + [item for item in new_items if item not in seen]
    return merged[-max_items:]


def _merge_tracked_items(
    existing: tuple[dict[str, object], ...],
    new_items: tuple[dict[str, object], ...],
    retired: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    retired_labels = {d.get("label", "") for d in retired}
    merged = list(existing)
    # Remove retired items
    merged = [d for d in merged if d.get("label", "") not in retired_labels]
    # Add new items (dedup by label)
    seen = {d.get("label", "") for d in merged}
    for d in new_items:
        label = d.get("label", "")
        if label and label not in seen:
            merged.append(d)
            seen.add(label)
    return tuple(merged)


class ReasonService:
    """User-intent operations and state transitions for reasoning threads."""

    def __init__(
        self,
        project_root: Path | None = None,
        repository: ReasonRepository | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
        trace_recorder: TraceRecorder | None = None,
        advancer: Any | None = None,
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
        self._advancer = advancer

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
        topic: str,
        *,
        working_summary: str = "",
        evidence_refs: tuple[str, ...] = (),
        source_trace_ids: tuple[str, ...] = (),
        priority: str = "normal",
        active_items: tuple[dict[str, object], ...] = (),
        mandates: tuple[str, ...] = (),
    ) -> ReasoningThread:
        active = self._repository.list_threads(status="active")
        if len(active) >= MAX_ACTIVE_THREADS:
            active_names = "\n".join(f"  - {t.id}: {t.topic[:60]}" for t in active)
            raise RuntimeError(
                f"Cannot start new thread: already {len(active)} active threads "
                f"(max {MAX_ACTIVE_THREADS}). Please pause, resolve, or archive one first.\n"
                f"Active threads:\n{active_names}"
            )

        thread = ReasoningThread(
            topic=topic.strip(),
            working_summary=working_summary.strip(),
            priority="normal" if priority not in ("normal", "high") else priority,  # type: ignore[arg-type]
            evidence_refs=list(evidence_refs),
            active_items_data=tuple(active_items),
            mandates_data=tuple(mandates),
        )
        saved = self._repository.save_thread(thread)
        workspace = self._workspace_store.ensure(thread.id)
        if self._trace_recorder is not None:
            self._trace_recorder.record_reason_thread_created(
                thread=saved,
                source_trace_ids=list(source_trace_ids),
                metadata={"workspace": str(workspace.root), "mandates": list(thread.mandates_data)},
            )

        write_log_event(
            "reasoning",
            "thread_started",
            f"Started reasoning thread: {thread.topic[:80]}",
            project_root=self._project_root,
            status="created",
            metadata={"thread_id": thread.id, "topic": thread.topic, "workspace": str(workspace.root)},
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
            f"Advancing reasoning thread: {thread.topic[:80]}",
            project_root=self._project_root,
            status="started",
            metadata={"thread_id": thread.id},
        )

        if step is not None:
            pass
        elif self._advancer is not None:
            generated = self._advancer.advance(thread)
            if generated is not None:
                step = generated
            else:
                step = ReasoningStep(
                    thread_id=thread.id,
                    kind="progress",
                    summary=f"Manual advance requested for: {thread.topic[:80]}",
                    delta="Advance requested but LLM did not produce a step — you may need to configure an API key.",
                    evidence_refs=list(thread.evidence_refs),
                )
        else:
            step = ReasoningStep(
                thread_id=thread.id,
                kind="progress",
                summary=f"Manual advance requested for: {thread.topic[:80]}",
                delta="Manual advance placeholder — LLM integration deferred.",
                evidence_refs=list(thread.evidence_refs),
            )

        now = datetime.now(UTC).isoformat()
        updated = ReasoningThread(
            id=thread.id,
            topic=thread.topic,
            status=thread.status,
            working_summary=_pick_working_summary(step, thread),
            hypotheses=_merge_str_lists(thread.hypotheses, step.new_hypotheses if step else [], max_items=_MAX_HYPOTHESES),
            open_questions=_merge_str_lists(thread.open_questions, step.new_open_questions if step else [], max_items=_MAX_OPEN_QUESTIONS),
            evidence_refs=_merge_str_lists(thread.evidence_refs, step.evidence_refs if step else [], max_items=_MAX_EVIDENCE_REFS),
            priority=thread.priority,
            last_advanced_at=now,
            next_review_after=thread.next_review_after,
            created_at=thread.created_at,
            updated_at=now,
            active_items_data=_merge_tracked_items(thread.active_items_data, step.new_findings_data if step else (), step.retired_findings_data if step else ()),
            pending_items_data=_merge_tracked_items(thread.pending_items_data, step.new_pending_data if step else (), ()),
            next_steps_data=step.next_steps_data if step and step.next_steps_data else thread.next_steps_data,
            mandates_data=thread.mandates_data,
        )
        with self._repository.batch_write():
            self._repository.save_step(step)
            self._repository.save_thread(updated)
        if self._trace_recorder is not None:
            self._trace_recorder.record_reason_step(thread=updated, step=step)

        write_log_event(
            "reasoning",
            "advance_completed",
            f"Advance completed for thread: {thread.topic[:80]}",
            project_root=self._project_root,
            status="completed",
            metadata={
                "thread_id": thread.id,
                "step_id": step.id,
                "step_kind": step.kind,
                "new_findings": len(step.new_findings_data) if step else 0,
                "new_pending": len(step.new_pending_data) if step else 0,
                "retired_findings": len(step.retired_findings_data) if step else 0,
                "next_steps": len(step.next_steps_data) if step else 0,
            },
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
            f"Deleted reasoning thread: {thread.topic[:80]}",
            project_root=self._project_root,
            status="deleted",
            metadata={"thread_id": thread.id, "topic": thread.topic},
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
