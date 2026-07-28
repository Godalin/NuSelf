"""Reason-owned framework tool definitions."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.tools.common import structured_tool_factory
from nuself.handles import VisibleHandleError, parse_visible_index
from nuself.reason.audit import write_reason_audit
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.errors import ReasonNotFound
from nuself.reason.output import ReasonOutputService, SectionPlanner
from nuself.reason.service import ReasonService
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.jobs import JobSink


def build_reason_tools(
    *,
    service: ReasonService,
    project_root: Path | None,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
) -> tuple[BaseTool, ...]:
    """Build the reason service's chat tools."""
    tool_from_function = structured_tool_factory()

    def list_active_reasoning_threads() -> str:
        """List all long-run reasoning threads."""
        threads = service.list_threads(status="all")
        if not threads:
            return _json_result({"threads": [], "count": 0})
        return _json_result(
            {
                "threads": [
                    {
                        "index": index,
                        "id": thread.id,
                        "topic": thread.topic,
                        "status": thread.status,
                        "priority": thread.priority,
                        "working_summary": thread.working_summary,
                        "step_count": len(service.list_steps(thread.id)),
                        "created_at": thread.created_at,
                        "last_advanced_at": thread.last_advanced_at,
                    }
                    for index, thread in enumerate(threads)
                ],
                "count": len(threads),
            }
        )

    def count_reasoning_threads() -> str:
        """Count all long-run reasoning threads."""
        threads = service.list_threads(status="all")
        by_status: dict[str, int] = {}
        for thread in threads:
            by_status[thread.status] = by_status.get(thread.status, 0) + 1
        return _json_result(
            {"count": len(threads), "by_status": by_status}
        )

    def show_reasoning_thread(thread_id: str) -> str:
        """Show one long-run reasoning thread. Use "current" for the latest."""
        tid = thread_id.strip()
        if not tid:
            return "Error: thread_id must be a non-empty string"
        if tid.lower() == "current":
            threads = service.list_threads(status="all")
            if not threads:
                return _json_error("No reasoning threads.")
            thread = threads[-1]
            return _json_result(
                _reason_show_payload(
                    thread,
                    service.list_steps(thread.id),
                )
            )
        try:
            thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(diagnostic_exception_message(exc))
        return _json_result(
            _reason_show_payload(thread, service.list_steps(thread.id))
        )

    def show_reasoning_context(thread_id: str) -> str:
        """Show one reasoning thread's global settings and current state."""
        tid = thread_id.strip()
        if not tid:
            return _json_error("thread_id must be a non-empty string")
        try:
            if tid.lower() == "current":
                threads = service.list_threads(status="all")
                if not threads:
                    return _json_error("No reasoning threads.")
                thread = threads[-1]
            else:
                thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(diagnostic_exception_message(exc))
        steps = service.list_steps(thread.id)
        return _json_result(
            {
                "thread": _reason_thread_payload(thread),
                "step_count": len(steps),
                "tool_logs": "omitted",
            }
        )

    def show_reasoning_step(thread_id: str, step: str) -> str:
        """Show one reasoning step by index, id, or 'latest'."""
        tid = thread_id.strip()
        step_ref = step.strip()
        if not tid:
            return _json_error("thread_id must be a non-empty string")
        if not step_ref:
            return _json_error("step must be a non-empty string")
        try:
            if tid.lower() == "current":
                threads = service.list_threads(status="all")
                if not threads:
                    return _json_error("No reasoning threads.")
                thread = threads[-1]
            else:
                thread = service.show_thread(tid)
        except ReasonNotFound as exc:
            return _json_error(diagnostic_exception_message(exc))
        steps = service.list_steps(thread.id)
        if not steps:
            return _json_error(
                f"No reasoning steps for thread: {thread.id}"
            )
        if step_ref.lower() == "latest":
            index = len(steps) - 1
            selected = steps[index]
        elif step_ref.isdigit():
            try:
                index = parse_visible_index(
                    step_ref,
                    count=len(steps),
                    label="reason step",
                )
            except VisibleHandleError as exc:
                return _json_error(diagnostic_exception_message(exc))
            selected = steps[index]
        else:
            matches = [
                candidate for candidate in steps
                if candidate.id == step_ref
            ]
            if not matches:
                return _json_error(
                    f"reason step not found: {step_ref}"
                )
            selected = matches[0]
            index = steps.index(selected)
        return _json_result(
            {
                "thread": {
                    "id": thread.id,
                    "topic": thread.topic,
                    "status": thread.status,
                },
                "step": _reason_step_payload(selected, index=index),
                "tool_logs": "omitted",
            }
        )

    def reason_propose(
        topic: str,
        working_summary: str,
        active_items: list[dict[str, object]],
        mandates: list[str],
    ) -> str:
        """Propose creating a long-run reasoning thread and start it after confirmation.

        Parameters:
          topic – the core topic for the thread.
          working_summary – enriched context from the discussion.
          active_items – initial tracked items, each with "label" (required),
            "description" (optional), "kind" (optional free-text tag).
          mandates – required actions the advancer MUST follow on every
            advance.
        """
        topic = topic.strip()
        if not topic:
            return "Error: topic must be a non-empty string"
        write_reason_audit(
            "proposal_created",
            project_root=project_root,
            metadata={
                "active_item_count": len(active_items),
                "mandate_count": len(mandates),
            },
        )
        thread = service.start_thread(
            topic=topic,
            working_summary=working_summary,
            active_items=tuple(active_items),
            mandates=tuple(mandates),
        )
        return thread.id

    def reason_export(
        thread_id: str,
        mode: str = "narrative",
        output_format: str = "markdown",
        start_index: int = 0,
        end_index: int | None = None,
        segment_size: int = 5,
    ) -> str:
        """Start a reason output export job and return after enqueueing it."""
        tid = thread_id.strip()
        if not tid:
            return "Error: thread_id must be a non-empty string"
        try:
            output_service = ReasonOutputService(
                project_root,
                job_sink=job_sink,
                section_planner=section_planner,
            )
            manifest = output_service.plan_job(
                tid,
                mode=mode,
                output_format=output_format,
                start_index=int(start_index),
                end_index=(
                    int(end_index)
                    if end_index is not None
                    else None
                ),
                segment_size=int(segment_size),
            )
        except (RuntimeError, ValueError, TypeError) as exc:
            return _json_error(diagnostic_exception_message(exc))
        paths = output_service.job_paths(tid, manifest.job_id)
        return _json_result(
            {
                "queued": True,
                "job": manifest.to_wire(),
                "paths": {
                    "root": str(paths.root),
                    "manifest": str(paths.manifest),
                    "progress": str(paths.progress),
                    "combined": str(paths.combined),
                    "chunks_dir": str(paths.chunks_dir),
                },
            }
        )

    decorators = import_module("nuself.decorators")
    composed_propose = decorators.audit_log("reasoning")(
        decorators.approval_required("reasoning")(reason_propose)
    )
    composed_export = decorators.audit_log("reasoning")(
        decorators.approval_required("reasoning")(reason_export)
    )
    return (
        tool_from_function(
            list_active_reasoning_threads,
            name="reason_list_active",
            description=(
                "List active and paused long-run reasoning threads. Use when the user asks about "
                "open questions, ongoing thinking, active reason threads, or what NuSelf is still considering."
            ),
            tags=("readonly",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            count_reasoning_threads,
            name="reason_count",
            description=(
                "Count active and paused long-run reasoning threads. Use when the user asks how many open "
                "questions or reasoning threads NuSelf is tracking."
            ),
            tags=("readonly",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            show_reasoning_thread,
            name="reason_show",
            description=(
                "Show details for a specific long-run reasoning thread, including current state and steps, "
                "but omitting tool logs. Pass 'current' to show the most recent active thread."
            ),
            tags=("readonly",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            show_reasoning_context,
            name="reason_context",
            description=(
                "Show one reasoning thread's global setup and current state only: topic, summary, mandates, "
                "active items, pending items, next steps, reasoning prompt, evidence refs, and step count. "
                "Does not include step bodies or tool logs. Pass 'current' to show the most recent active thread."
            ),
            tags=("readonly",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            show_reasoning_step,
            name="reason_step",
            description=(
                "Show one concrete reasoning step by 0-based step index, step id, or 'latest'. "
                "Returns the step summary, output, delta, findings, pending items, next steps, confidence, "
                "and evidence refs, but omits tool logs."
            ),
            tags=("readonly",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            composed_propose,
            name="reason_propose",
            description=(
                "Propose creating a new long-run thinking thread. "
                "Call this when the user explicitly wants to start a thread. "
                "The decorated tool wrapper will prompt for confirmation before writing the proposal. "
                "The thread tracks state as general-purpose tracked items (active_items, "
                "pending_items, next_steps) with free-text kind labels that adapt to the task "
                "— e.g. 'hypothesis', 'character', 'suspect', 'plot_thread', 'world_rule'. "
                "Tip: before proposing, consider using persona_list and persona_think to "
                "enrich the thread's initial context with different perspectives."
            ),
            tags=("write",),
            metadata={"service_component": "reasoning"},
        ),
        tool_from_function(
            composed_export,
            name="reason_export",
            description=(
                "Start a reason output export job for a thread and write the export workspace artifacts. "
                "Use when the user wants a long-form report, narrative, outline, or summary derived from a reason thread. "
                "Call this tool directly when the user asks for an export; do not wait for a separate confirmation turn. "
                "This is an approval-gated tool: during the call, the decorated wrapper prompts the user for confirmation and the returned structured JSON shows whether the user approved. "
                "If approved, the structured JSON includes the export job result. "
                "On approval, the underlying result contains the export job manifest and workspace paths, while the full composed output is stored in the thread workspace."
            ),
            tags=("write", "log"),
            metadata={"service_component": "reasoning"},
        ),
    )


def _json_result(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_error(message: str) -> str:
    return _json_result({"error": message})


def _reason_thread_payload(
    thread: ReasoningThread,
) -> dict[str, object]:
    return {
        "id": thread.id,
        "topic": thread.topic,
        "status": thread.status,
        "priority": thread.priority,
        "working_summary": thread.working_summary,
        "mandates": thread.mandates,
        "active_items": [item.to_wire() for item in thread.active_items],
        "pending_items": [item.to_wire() for item in thread.pending_items],
        "next_steps": [item.to_wire() for item in thread.next_steps],
        "reasoning_prompt": thread.reasoning_prompt,
        "evidence_refs": list(thread.evidence_refs),
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "last_advanced_at": thread.last_advanced_at,
        "next_review_after": thread.next_review_after,
        "skip_next_advance_until": thread.skip_next_advance_until,
    }


def _reason_step_payload(
    step: ReasoningStep,
    *,
    index: int,
) -> dict[str, object]:
    return {
        "index": index,
        "id": step.id,
        "thread_id": step.thread_id,
        "kind": step.kind,
        "summary": step.summary,
        "output": step.output,
        "delta": step.delta,
        "new_findings": [item.to_wire() for item in step.new_findings],
        "new_pending": [item.to_wire() for item in step.new_pending],
        "retired_findings": [
            item.to_wire() for item in step.retired_findings
        ],
        "next_steps": [item.to_wire() for item in step.next_steps],
        "evidence_refs": list(step.evidence_refs),
        "confidence": step.confidence,
        "terminal_status": step.terminal_status,
        "terminal_reason": step.terminal_reason,
        "created_at": step.created_at,
    }


def _reason_show_payload(
    thread: ReasoningThread,
    steps: list[ReasoningStep],
) -> dict[str, object]:
    return {
        "thread": _reason_thread_payload(thread),
        "step_count": len(steps),
        "steps": [
            _reason_step_payload(step, index=index)
            for index, step in enumerate(steps)
        ],
        "tool_logs": "omitted",
    }
