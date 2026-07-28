"""Daemon-side durable job worker for reason output export."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.agent.text import TextAgent, default_text_agent
from nuself.clock import utc_now_iso
from nuself.config import ConfigSystem
from nuself.daemon.workers import DaemonWorkerSupervisor
from nuself.logs import LogLevel, write_log_event
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputSection,
    ReasonOutputService,
)
from nuself.runtime.context import use_runtime_context
from nuself.runtime.jobs import JobMessage
from nuself.runtime.observability import (
    format_exception_chain,
    report_observed_failure,
    run_observed_best_effort,
)
from nuself.storage import write_json_atomic
from nuself.workspace import PrivateWorkspaceStore

MAX_EXPORT_ATTEMPTS = 5
EXPORT_RETRY_BASE_SECONDS = 10
EXPORT_RETRY_MAX_SECONDS = 600
EXPORT_QUEUE_POLL_SECONDS = 1.0
EXPORT_JOB_NAME = "reason.output.export"
EXPORT_WORKER_NAME = "export_worker"

SectionPlanner = Callable[
    [ReasoningThread, Sequence[ReasoningStep], str],
    tuple[ReasonOutputSection, ...],
]


class ReasonSectionOutput(BaseModel):
    """One exact generated section range."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    focus: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    step_start: int = Field(ge=0)
    step_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _range_is_ordered(self) -> ReasonSectionOutput:
        if self.step_start > self.step_end:
            raise ValueError("section step_start must not exceed step_end")
        return self


class ReasonSectionPlanOutput(BaseModel):
    """Exact generated chapter plan for one reason export."""

    model_config = ConfigDict(strict=True, extra="forbid")

    sections: list[ReasonSectionOutput] = Field(
        min_length=1,
        max_length=8,
    )


def _write_export_audit_event(
    event: str,
    message: str,
    *,
    project_root: Path,
    level: LogLevel = "info",
    status: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Project an export lifecycle event without changing worker control flow."""

    run_observed_best_effort(
        lambda: write_log_event(
            "daemon",
            event,
            message,
            project_root=project_root,
            level=level,
            status=status,
            metadata=metadata,
        ),
        component="daemon",
        event="export_audit_write_failed",
        message=f"Could not record export audit event {event}",
        project_root=project_root,
        metadata={"audit_event": event},
    )


@dataclass(frozen=True)
class ExportJobInspection:
    manifest: ReasonOutputManifest
    total_chunks: int | str
    progress_error: Exception | None = None

    @property
    def terminal(self) -> bool:
        return self.manifest.status in ("complete", "failed")


def inspect_export_job(
    manifest_path: Path,
    *,
    job_id: str,
    thread_id: str,
) -> ExportJobInspection:
    """Decode and correlate one export manifest and optional progress."""

    manifest = read_export_manifest(manifest_path)
    if manifest.job_id != job_id or manifest.thread_id != thread_id:
        raise ValueError(
            "export manifest identity does not match queue message"
        )
    if manifest.status in ("complete", "failed"):
        return ExportJobInspection(manifest=manifest, total_chunks="?")

    progress_path = manifest_path.with_name(manifest.progress_filename)
    try:
        progress = _read_export_progress(progress_path)
        if progress.job_id != job_id or progress.thread_id != thread_id:
            raise ValueError(
                "export progress identity does not match queue message"
            )
    except FileNotFoundError:
        return ExportJobInspection(manifest=manifest, total_chunks="?")
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        return ExportJobInspection(
            manifest=manifest,
            total_chunks="?",
            progress_error=exc,
        )
    return ExportJobInspection(
        manifest=manifest,
        total_chunks=progress.total_chunks,
    )


def persist_export_failure(
    manifest_path: Path,
    operation_error: Exception,
    *,
    max_attempts: int,
) -> ReasonOutputManifest:
    """Persist one failed composition attempt atomically."""

    manifest = read_export_manifest(manifest_path)
    attempts = manifest.attempts + 1
    updated = manifest.with_updates(
        status="failed" if attempts >= max_attempts else None,
        attempts=attempts,
        last_error=format_exception_chain(operation_error),
        last_attempt_at=utc_now_iso(),
    )
    write_json_atomic(manifest_path, updated.to_wire())
    return updated


def build_reason_export_section_planner(
    project_root: Path,
    *,
    agent: StructuredAgent[ReasonSectionPlanOutput] | None = None,
) -> SectionPlanner:
    """Return an instance-scoped typed-agent section planner."""

    lang = ConfigSystem.load(
        project_root=project_root
    ).chat.language_preference
    section_agent = (
        agent
        if agent is not None
        else default_structured_agent(
            ReasonSectionPlanOutput,
            project_root=project_root,
            component="reasoning",
        )
    )

    def planner(
        thread: ReasoningThread,
        steps: Sequence[ReasoningStep],
        mode: str,
    ) -> tuple[ReasonOutputSection, ...]:
        from nuself.reason.output import plan_sections as fallback_plan

        if not steps:
            return fallback_plan(thread, list(steps), mode=mode)
        step_lines: list[str] = []
        for index, step in enumerate(steps):
            step_lines.append(f"  {index}. summary: {step.summary}")
            if step.output:
                step_lines.append(f"     output: {step.output[:200]}")
            elif step.delta:
                step_lines.append(f"     delta: {step.delta[:200]}")
        steps_text = "\n".join(step_lines)

        prompt = (
            "Organize the following reason steps into 2–8 chapters.\n"
            "For each chapter provide:\n"
            '- "title" — a descriptive chapter title\n'
            '- "focus" — what this chapter should cover\n'
            '- "step_start" — index of the first step (0-based)\n'
            '- "step_end" — index of the last step (inclusive)\n\n'
            "Ranges must form one ordered contiguous partition covering every "
            "step exactly once.\n\n"
            f"Steps:\n{steps_text}"
        )
        try:
            output = section_agent.invoke(
                [
                    SystemMessage(
                        content=(
                            f"You are planning a {mode} for reason thread "
                            f"'{thread.topic}'. Write in {lang}."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            sections = _materialize_section_plan(output, steps)
        except ValueError:
            return fallback_plan(thread, list(steps), mode=mode)
        return tuple(
            ReasonOutputSection(
                index=index,
                title=section.title,
                focus=section.focus,
                step_ids=tuple(
                    steps[position].id
                    for position in range(
                        section.step_start,
                        section.step_end + 1,
                    )
                ),
                source_start_index=section.step_start,
                source_end_index=section.step_end,
                summary=section.focus[:80],
            )
            for index, section in enumerate(sections)
        )

    return planner


class ReasonExportWorker:
    """Own the daemon-side queue, retries, and recovery of export jobs."""

    def __init__(
        self,
        project_root: Path,
        shutdown_requested: threading.Event,
        supervisor: DaemonWorkerSupervisor,
        *,
        text_agent: TextAgent | None = None,
    ) -> None:
        self._project_root = project_root
        self._shutdown_requested = shutdown_requested
        self._supervisor = supervisor
        self._text_agent = (
            text_agent
            if text_agent is not None
            else default_text_agent(
                project_root=project_root,
                component="reasoning",
            )
        )
        self._queue: queue.SimpleQueue[JobMessage] = queue.SimpleQueue()
        self._stopping = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._timers: list[threading.Timer] = []
        self._timers_lock = threading.Lock()
        self._store: PrivateWorkspaceStore | None = None
        self._service: ReasonOutputService | None = None

    def enqueue(self, message: JobMessage) -> None:
        """Enqueue one typed export job message."""

        with self._lifecycle_lock:
            if self._stopping.is_set():
                return
            self._queue.put(message)

    def prepare(self) -> None:
        """Construct dependencies before the owned worker thread starts."""

        if self._store is not None or self._service is not None:
            return
        store = PrivateWorkspaceStore(self._project_root, scope="reason")
        service = ReasonOutputService(self._project_root)
        self._store = store
        self._service = service

    def stop(self) -> None:
        """Cancel retry timers and drain work that cannot be processed."""

        self._stopping.set()
        with self._timers_lock:
            for timer in self._timers:
                timer.cancel()
            self._timers.clear()
        drained = 0
        with self._lifecycle_lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    drained += 1
                except queue.Empty:
                    break
        if drained:
            _write_export_audit_event(
                "export_queue_drained",
                f"Drained {drained} unprocessed export jobs",
                project_root=self._project_root,
                level="warning",
            )

    @property
    def pending_retry_count(self) -> int:
        with self._timers_lock:
            return len(self._timers)

    def run(self) -> None:
        """Reconcile durable jobs, then process queue messages until shutdown."""

        store, _ = self._dependencies()
        self._reconcile(store)
        while not self._shutdown_requested.is_set():
            try:
                message = self._queue.get(
                    timeout=EXPORT_QUEUE_POLL_SECONDS
                )
            except queue.Empty:
                continue
            except Exception as exc:
                report_observed_failure(
                    exc,
                    component="daemon",
                    event="export_worker_get_error",
                    message="Export queue read failed",
                    project_root=self._project_root,
                    level="warning",
                    status="error",
                    metadata=None,
                )
                continue
            if self._shutdown_requested.is_set():
                break
            message_context = replace(
                message.envelope.context,
                thread_id=message.resource_id,
                job_id=message.job_id,
                source="daemon.worker.export_worker",
            )
            with use_runtime_context(message_context):
                self._process(message)

    def _process(self, message: JobMessage) -> None:
        if message.envelope.name != EXPORT_JOB_NAME:
            _write_export_audit_event(
                "export_job_type_ignored",
                (
                    "Ignored unsupported export job type "
                    f"{message.envelope.name}"
                ),
                project_root=self._project_root,
                level="warning",
                metadata={"message_id": message.envelope.message_id},
            )
            return
        thread_id = message.resource_id
        job_id = message.job_id
        _write_export_audit_event(
            "export_job_dequeued",
            f"Processing export job {job_id} for thread {thread_id}",
            project_root=self._project_root,
            metadata={"job_id": job_id, "thread_id": thread_id},
        )

        store, service = self._dependencies()
        manifest_path = (
            store.paths(thread_id).artifacts
            / "export"
            / "jobs"
            / job_id
            / "manifest.json"
        )
        try:
            inspection = inspect_export_job(
                manifest_path,
                job_id=job_id,
                thread_id=thread_id,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as exc:
            self._supervisor.record_failure(EXPORT_WORKER_NAME, exc)
            report_observed_failure(
                exc,
                component="daemon",
                event="export_job_manifest_invalid",
                message=(
                    f"Cannot process export job {job_id}: invalid manifest"
                ),
                project_root=self._project_root,
                level="error",
                status="error",
                metadata={"job_id": job_id, "thread_id": thread_id},
            )
            return
        if inspection.terminal:
            return
        if inspection.progress_error is not None:
            report_observed_failure(
                inspection.progress_error,
                component="daemon",
                event="export_job_progress_invalid",
                message=(
                    f"Ignoring invalid progress for export job {job_id}"
                ),
                project_root=self._project_root,
                level="warning",
                status="degraded",
                metadata={"job_id": job_id, "thread_id": thread_id},
            )
        _write_export_audit_event(
            "export_job_composition_started",
            (
                f"Composing {inspection.total_chunks} chunk(s) "
                f"for job {job_id}"
            ),
            project_root=self._project_root,
            metadata={
                "job_id": job_id,
                "thread_id": thread_id,
                "chunks": inspection.total_chunks,
            },
        )
        try:
            service.compose_with_runner(
                thread_id,
                job_id,
                self._llm_runner,
            )
            self._supervisor.record_success(EXPORT_WORKER_NAME)
        except Exception as exc:
            self._supervisor.record_failure(EXPORT_WORKER_NAME, exc)
            self._handle_composition_failure(
                manifest_path,
                message,
                exc,
            )

    def _handle_composition_failure(
        self,
        manifest_path: Path,
        message: JobMessage,
        operation_error: Exception,
    ) -> None:
        thread_id = message.resource_id
        job_id = message.job_id
        try:
            failed_manifest = persist_export_failure(
                manifest_path,
                operation_error,
                max_attempts=MAX_EXPORT_ATTEMPTS,
            )
        except Exception as state_error:
            report_observed_failure(
                state_error,
                component="daemon",
                event="export_job_state_persist_failed",
                message=(
                    f"Could not persist failure state for export job {job_id}"
                ),
                project_root=self._project_root,
                level="error",
                status="error",
                metadata={
                    "job_id": job_id,
                    "thread_id": thread_id,
                    "operation_error": format_exception_chain(
                        operation_error
                    ),
                },
            )
            return
        attempts = failed_manifest.attempts
        if attempts >= MAX_EXPORT_ATTEMPTS:
            report_observed_failure(
                operation_error,
                component="daemon",
                event="export_job_failed",
                message=(
                    f"Export job {job_id} exhausted retries: "
                    f"{operation_error!s}"
                ),
                project_root=self._project_root,
                level="error",
                status="error",
                metadata={
                    "job_id": job_id,
                    "thread_id": thread_id,
                    "attempts": attempts,
                },
            )
            return
        if self._stopping.is_set() or self._shutdown_requested.is_set():
            return
        backoff = _next_backoff(attempts)
        _write_export_audit_event(
            "export_job_retry",
            (
                f"Export job {job_id} will retry in {backoff}s "
                f"(attempt {attempts})"
            ),
            project_root=self._project_root,
            status="retry",
            metadata={
                "job_id": job_id,
                "thread_id": thread_id,
                "attempts": attempts,
                "next_backoff": backoff,
            },
        )
        with self._timers_lock:
            if (
                self._stopping.is_set()
                or self._shutdown_requested.is_set()
            ):
                return
            self._timers = [
                timer for timer in self._timers if timer.is_alive()
            ]
            retry_message = JobMessage.create(
                name=EXPORT_JOB_NAME,
                producer="daemon.retry",
                job_id=job_id,
                resource_id=thread_id,
                payload={"attempt": attempts + 1},
            )
            timer = threading.Timer(
                backoff,
                self.enqueue,
                args=(retry_message,),
            )
            self._timers.append(timer)
            timer.start()

    def _reconcile(self, store: PrivateWorkspaceStore) -> None:
        reconciled = 0
        for owner_id in store.list_owners():
            jobs_dir = store.paths(owner_id).artifacts / "export" / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in sorted(jobs_dir.iterdir()):
                if not job_dir.is_dir():
                    continue
                lock_path = job_dir / ".lock"
                if lock_path.exists():
                    lock_path.unlink(missing_ok=True)
                manifest_path = job_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = read_export_manifest(manifest_path)
                except (
                    OSError,
                    json.JSONDecodeError,
                    ValueError,
                    KeyError,
                ) as exc:
                    self._supervisor.record_failure(
                        EXPORT_WORKER_NAME,
                        exc,
                    )
                    report_observed_failure(
                        exc,
                        component="daemon",
                        event="export_reconciliation_skip",
                        message=(
                            "Skipping invalid export manifest for "
                            f"{job_dir.name}"
                        ),
                        project_root=self._project_root,
                        level="warning",
                        status="error",
                        metadata={
                            "thread_id": owner_id,
                            "job_id": job_dir.name,
                        },
                    )
                    continue
                if manifest.status in ("complete", "failed"):
                    continue
                self.enqueue(
                    JobMessage.create(
                        name=EXPORT_JOB_NAME,
                        producer="daemon.reconciliation",
                        job_id=manifest.job_id,
                        resource_id=owner_id,
                    )
                )
                reconciled += 1
        _write_export_audit_event(
            "export_queue_reconciled",
            (
                "Export queue reconciled on startup; re-enqueued "
                f"{reconciled} job(s)"
            ),
            project_root=self._project_root,
            metadata={"replayed_jobs": reconciled},
        )

    def _llm_runner(
        self,
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        steps: Sequence[ReasoningStep],
        *,
        section: ReasonOutputSection,
        section_plan: Sequence[ReasonOutputSection],
        index: int,
        total: int,
    ) -> str:
        del index, total
        lang = ConfigSystem.load(
            project_root=self._project_root
        ).chat.language_preference
        system = (
            f"You are a writing assistant. Compose a {manifest.mode} in "
            f"{manifest.output_format} format from the provided reason steps. "
            f"Write in {lang}. Produce plain Markdown paragraphs — do NOT "
            "include headings or section titles, they will be added "
            "automatically. Keep terminology and tone consistent across all "
            "chunks."
        )
        body_lines = [
            "",
            f"Current section: {section.title}",
            f"Section focus: {section.focus}",
            "",
            "Global section plan:",
        ]
        for planned in section_plan:
            marker = " (current)" if planned.index == section.index else ""
            body_lines.append(
                f"  - {planned.index + 1}. {planned.title}: "
                f"{planned.focus}{marker}"
            )
        for step in steps:
            body_lines.append("---")
            body_lines.append(f"Step: {step.summary}")
            if step.output:
                body_lines.append(step.output)
            elif step.delta:
                body_lines.append(step.delta)
            if step.evidence_refs:
                body_lines.append("Evidence:")
                body_lines.extend(f"- {ref}" for ref in step.evidence_refs)
        return self._text_agent.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content="\n".join(body_lines)),
            ]
        )

    def _dependencies(
        self,
    ) -> tuple[PrivateWorkspaceStore, ReasonOutputService]:
        if self._store is None or self._service is None:
            raise RuntimeError(
                "export worker dependencies were not initialized"
            )
        return self._store, self._service


def read_export_manifest(path: Path) -> ReasonOutputManifest:
    return ReasonOutputManifest.from_wire(_read_json_object(path))


def _read_export_progress(path: Path) -> ReasonOutputProgress:
    return ReasonOutputProgress.from_wire(_read_json_object(path))


def _read_json_object(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], raw)


def _materialize_section_plan(
    output: ReasonSectionPlanOutput,
    steps: Sequence[ReasoningStep],
) -> tuple[ReasonSectionOutput, ...]:
    expected_start = 0
    for section in output.sections:
        if section.step_start != expected_start:
            raise ValueError(
                "section ranges must be ordered, contiguous, and non-overlapping"
            )
        if section.step_end >= len(steps):
            raise ValueError("section range exceeds available reason steps")
        expected_start = section.step_end + 1
    if expected_start != len(steps):
        raise ValueError("section ranges must cover every reason step")
    return tuple(output.sections)


def _next_backoff(attempts: int) -> int:
    return min(
        EXPORT_RETRY_MAX_SECONDS,
        EXPORT_RETRY_BASE_SECONDS * (2 ** (attempts - 1)),
    )
