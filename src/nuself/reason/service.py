"""Reason subsystem service."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Protocol

from nuself.runtime.clock import utc_now_iso
from nuself.reason.audit import REASON_AUDIT
from nuself.reason.model import ReasoningStep, ReasoningThread, ReasonPriority, ReasonStatus, TerminalStatus
from nuself.reason.errors import (
    ReasonAdvanceError,
    ReasonPromptError,
    ReasonTransitionError,
)
from nuself.reason.repository import ReasonRepository
from nuself.trace.service import TraceRecorder
from nuself.storage.workspace import PrivateWorkspacePaths, PrivateWorkspaceStore
from nuself.inbox.model import InboxItem
from nuself.inbox.service import InboxService

_MAX_EVIDENCE_REFS = 20

type ReasonStepObserver = Callable[
    [ReasoningThread, ReasoningStep, str | None], object
]


def _step_requires_attention(step: ReasoningStep) -> bool:
    """Keep internal no-op advancement out of the user's Inbox."""

    return step.kind != "no_change" and bool(
        step.summary.strip()
        or step.new_findings_data
        or step.new_pending_data
        or step.terminal_status
    )


class ReasonAdvancerProtocol(Protocol):
    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate one reasoning step for a thread."""


def _merge_str_lists(
    existing: Sequence[str],
    new_items: Sequence[str],
    *,
    max_items: int = 10,
) -> tuple[str, ...]:
    seen = set(existing)
    merged = (*existing, *(item for item in new_items if item not in seen))
    return merged[-max_items:]


def _merge_tracked_items(
    existing: tuple[Mapping[str, object], ...],
    new_items: tuple[Mapping[str, object], ...],
    retired: tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], ...]:
    retired_labels = {d.get("label", "") for d in retired}
    merged = list(existing)
    merged = [d for d in merged if d.get("label", "") not in retired_labels]
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
        project_root: Path,
        *,
        repository: ReasonRepository,
        workspace_store: PrivateWorkspaceStore,
        trace_recorder: TraceRecorder,
        prompt_generator: Callable[..., str],
        inbox: InboxService,
        step_observer: ReasonStepObserver | None = None,
    ) -> None:
        self._repository = repository
        self._project_root = project_root
        self._workspace_store = workspace_store
        self._trace_recorder = trace_recorder
        self._prompt_generator = prompt_generator
        self._inbox = inbox
        self._step_observer = step_observer

    # ── Read ───────────────────────────────────────────────────────

    def list_threads(self, status: str | None = "all") -> list[ReasoningThread]:
        return self._repository.list_threads(status=status)

    def show_thread(self, id_or_index: str) -> ReasoningThread:
        return self._repository.resolve_thread(id_or_index)

    def list_steps(self, thread_id: str) -> list[ReasoningStep]:
        return self._repository.list_steps(thread_id)

    def workspace_paths(self, thread_id: str) -> PrivateWorkspacePaths:
        """Resolve Reason-owned artifacts for one thread."""

        return self._workspace_store.paths(thread_id)

    def list_workspace_owners(self) -> list[str]:
        """List thread workspaces for export recovery."""

        return self._workspace_store.list_owners()

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
        priority_value: ReasonPriority = "high" if priority == "high" else "normal"
        reasoning_prompt = self._prompt_generator(
            topic,
            mandates=mandates,
            active_items=tuple(active_items),
        ).strip()
        if not reasoning_prompt:
            raise ReasonPromptError(
                "Cannot start reason thread: reasoning prompt generation "
                "returned empty output"
            )

        thread = ReasoningThread(
            topic=topic.strip(),
            working_summary=working_summary.strip(),
            priority=priority_value,
            evidence_refs=evidence_refs,
            active_items_data=tuple(active_items),
            mandates_data=tuple(mandates),
            reasoning_prompt=reasoning_prompt,
        )
        saved = self._repository.save_thread(thread)
        workspace = self._workspace_store.paths(thread.id)
        REASON_AUDIT.observe(
            lambda: self._trace_recorder.record_reason_thread_created(
                thread=saved,
                source_trace_ids=list(source_trace_ids),
                metadata={
                    "workspace": str(workspace.root),
                    "mandates": list(thread.mandates_data),
                },
            ),
            event="trace_recording_failed",
            project_root=self._project_root,
            metadata={
                "operation": "start_thread",
                "thread_id": saved.id,
                "step_id": None,
            },
        )

        REASON_AUDIT.write(
            "thread_started",
            project_root=self._project_root,
            metadata={"thread_id": thread.id},
        )
        return saved

    def start_thread_once(
        self,
        operation_id: str,
        topic: str,
        *,
        working_summary: str = "",
        priority: str = "normal",
        active_items: tuple[dict[str, object], ...] = (),
        mandates: tuple[str, ...] = (),
    ) -> ReasoningThread:
        """Create once for a stable caller-owned operation identity."""
        key = operation_id.strip()
        if not key:
            raise ValueError("operation_id must be a non-empty string")
        topic_value = topic.strip()
        summary_value = working_summary.strip()
        priority_value: ReasonPriority = (
            "high" if priority == "high" else "normal"
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "topic": topic_value,
                    "working_summary": summary_value,
                    "priority": priority_value,
                    "active_items": active_items,
                    "mandates": mandates,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        replay = self._repository.replay_thread(
            operation_id=key,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        reasoning_prompt = self._prompt_generator(
            topic_value,
            mandates=mandates,
            active_items=active_items,
        ).strip()
        if not reasoning_prompt:
            raise ReasonPromptError(
                "Cannot start reason thread: reasoning prompt generation "
                "returned empty output"
            )
        candidate = ReasoningThread(
            topic=topic_value,
            working_summary=summary_value,
            priority=priority_value,
            active_items_data=active_items,
            mandates_data=mandates,
            reasoning_prompt=reasoning_prompt,
        )
        saved, created = self._repository.create_thread_once(
            candidate,
            operation_id=key,
            fingerprint=fingerprint,
        )
        if not created:
            return saved
        workspace = self._workspace_store.paths(saved.id)
        REASON_AUDIT.observe(
            lambda: self._trace_recorder.record_reason_thread_created(
                thread=saved,
                source_trace_ids=[],
                metadata={
                    "workspace": str(workspace.root),
                    "mandates": list(saved.mandates_data),
                    "operation_id": key,
                },
            ),
            event="trace_recording_failed",
            project_root=self._project_root,
            metadata={
                "operation": "start_thread",
                "thread_id": saved.id,
                "step_id": None,
            },
        )
        REASON_AUDIT.write(
            "thread_started",
            project_root=self._project_root,
            metadata={"thread_id": saved.id},
        )
        return saved

    def advance_thread(
        self,
        id_or_index: str,
        *,
        step: ReasoningStep | None = None,
        advancer: ReasonAdvancerProtocol | None = None,
    ) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index)

        if thread.status != "active":
            raise ReasonAdvanceError(
                f"Cannot advance thread {thread.id}: status is "
                f"'{thread.status}', expected 'active'"
            )

        REASON_AUDIT.write(
            "advance_started",
            project_root=self._project_root,
            metadata={"thread_id": thread.id},
        )

        if step is None and advancer is not None:
            generated = advancer.advance(thread)
            if generated is not None:
                step = generated
            else:
                raise ReasonAdvanceError(
                    f"Cannot advance thread {thread.id}: advancer did not "
                    "produce a structured step"
                )
        elif step is None:
            raise ReasonAdvanceError(
                f"Cannot advance thread {thread.id}: no reason advancer configured"
            )

        now = utc_now_iso()
        terminal_status = step.terminal_status
        final_status = _status_from_terminal_status(terminal_status) or thread.status
        updated = ReasoningThread(
            id=thread.id,
            topic=thread.topic,
            status=final_status,
            working_summary=step.summary or thread.working_summary,
            evidence_refs=_merge_str_lists(
                thread.evidence_refs,
                step.evidence_refs,
                max_items=_MAX_EVIDENCE_REFS,
            ),
            priority=thread.priority,
            last_advanced_at=now,
            next_review_after=thread.next_review_after,
            skip_next_advance_until=thread.skip_next_advance_until,
            created_at=thread.created_at,
            updated_at=now,
            active_items_data=_merge_tracked_items(
                thread.active_items_data,
                step.new_findings_data,
                step.retired_findings_data,
            ),
            pending_items_data=_merge_tracked_items(
                thread.pending_items_data,
                step.new_pending_data,
                (),
            ),
            next_steps_data=step.next_steps_data or thread.next_steps_data,
            mandates_data=thread.mandates_data,
            reasoning_prompt=thread.reasoning_prompt,
        )
        with self._repository.batch_write():
            self._repository.save_step(step)
            self._repository.save_thread(updated)
        if _step_requires_attention(step):
            self._inbox.add(
                InboxItem(
                    id=f"inbox-reason-step-{step.id}",
                    kind="reason_step",
                    source_id=step.id,
                    title=f"Reason update: {updated.topic}",
                    body=step.summary,
                    idempotency_key=f"reason-step-{step.id}",
                )
            )
        trace = REASON_AUDIT.observe(
            lambda: self._trace_recorder.record_reason_step(
                thread=updated,
                step=step,
            ),
            event="trace_recording_failed",
            project_root=self._project_root,
            metadata={
                "operation": "advance_thread",
                "thread_id": updated.id,
                "step_id": step.id,
            },
        )
        if self._step_observer is not None:
            self._step_observer(
                updated,
                step,
                trace.id if trace is not None else None,
            )

        REASON_AUDIT.write(
            "advance_completed",
            project_root=self._project_root,
            metadata={
                "thread_id": thread.id,
                "step_id": step.id,
                "step_kind": step.kind,
                "new_findings": len(step.new_findings_data),
                "new_pending": len(step.new_pending_data),
                "retired_findings": len(step.retired_findings_data),
                "next_steps": len(step.next_steps_data),
            },
        )
        if final_status != thread.status:
            REASON_AUDIT.write(
                "terminal_recommendation_applied",
                project_root=self._project_root,
                metadata={
                    "thread_id": thread.id,
                    "step_id": step.id,
                    "terminal_status": terminal_status,
                    "from_status": thread.status,
                    "to_status": final_status,
                },
            )
        return updated

    def pause_thread(self, id_or_index: str) -> ReasoningThread:
        return self._transition(id_or_index, "paused")

    def resume_thread(self, id_or_index: str) -> ReasoningThread:
        return self._transition(id_or_index, "active")

    def resolve_thread(self, id_or_index: str) -> ReasoningThread:
        return self._transition(id_or_index, "resolved")

    def archive_thread(self, id_or_index: str) -> ReasoningThread:
        return self._transition(id_or_index, "archived")

    def delete_thread(self, id_or_index: str) -> str:
        thread = self._repository.resolve_thread(id_or_index)

        import shutil
        ws = self._workspace_store.paths(thread.id)
        if ws.root.exists():
            shutil.rmtree(ws.root)

        self._repository.delete_thread(thread.id)
        REASON_AUDIT.write(
            "thread_deleted",
            project_root=self._project_root,
            metadata={"thread_id": thread.id},
        )
        return thread.id

    def defer_advancement(
        self,
        id_or_index: str,
        *,
        until: str,
    ) -> ReasoningThread:
        """Persist the next scheduler-eligible time for one thread."""

        thread = self._repository.resolve_thread(id_or_index)
        updated = replace(thread, skip_next_advance_until=until)
        return self._repository.save_thread(updated)

    # ── Internal ───────────────────────────────────────────────────

    def _transition(
        self,
        id_or_index: str,
        new_status: ReasonStatus,
    ) -> ReasoningThread:
        thread = self._repository.resolve_thread(id_or_index)
        allowed: dict[ReasonStatus, tuple[ReasonStatus, ...]] = {
            "active": ("paused", "resolved", "archived"),
            "paused": ("active", "resolved", "archived"),
            "resolved": ("archived",),
            "archived": (),
        }
        if thread.status not in allowed or new_status not in allowed[thread.status]:
            raise ReasonTransitionError(
                f"Cannot transition thread {thread.id} from "
                f"'{thread.status}' to '{new_status}'"
            )

        updated = thread.with_status(new_status)
        self._repository.save_thread(updated)

        REASON_AUDIT.write(
            "thread_status_changed",
            project_root=self._project_root,
            metadata={"thread_id": thread.id, "from_status": thread.status, "to_status": new_status},
        )
        return updated


def _status_from_terminal_status(status: TerminalStatus) -> ReasonStatus | None:
    if status == "suggest_resolved":
        return "resolved"
    if status == "suggest_paused":
        return "paused"
    return None
