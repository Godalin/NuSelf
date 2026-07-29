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
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputSection,
    ReasonOutputService,
)
from nuself.reason.audit import (
    report_reason_failure,
    write_reason_audit,
)
from nuself.runtime.context import use_runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.jobs import (
    JobAdmissionQueue,
    JobAdmissionResult,
    JobMessage,
)
from nuself.runtime.job_definitions import JobDefinitionRegistry
from nuself.storage import write_json_atomic
from nuself.workspace import PrivateWorkspaceStore

MAX_EXPORT_ATTEMPTS = 5
EXPORT_RETRY_BASE_SECONDS = 10
EXPORT_RETRY_MAX_SECONDS = 600
EXPORT_QUEUE_POLL_SECONDS = 1.0
EXPORT_QUEUE_CAPACITY = 256
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
        last_error=diagnostic_exception_chain(operation_error),
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
        job_definitions: JobDefinitionRegistry | None = None,
        queue_capacity: int = EXPORT_QUEUE_CAPACITY,
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
        self._job_definitions = (
            job_definitions
            if job_definitions is not None
            else build_reason_job_definition_registry()
        )
        self._queue = JobAdmissionQueue(queue_capacity)
        self._reconciliation_requested = threading.Event()
        self._stopping = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._timers: list[threading.Timer] = []
        self._retry_job_keys: set[tuple[str, str]] = set()
        self._timers_lock = threading.Lock()
        self._store: PrivateWorkspaceStore | None = None
        self._service: ReasonOutputService | None = None

    def enqueue(self, message: JobMessage) -> None:
        """Enqueue one typed export job message."""

        self._job_definitions.validate(message)
        self._admit(message)

    def _admit(
        self,
        message: JobMessage,
    ) -> JobAdmissionResult | None:
        with self._lifecycle_lock:
            if self._stopping.is_set():
                return None
            result = self._queue.admit(message)
            if result == "full":
                self._reconciliation_requested.set()
            return result

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
            self._retry_job_keys.clear()
        with self._lifecycle_lock:
            drained = len(self._queue.drain())
        if drained:
            write_reason_audit(
                "export_queue_drained",
                project_root=self._project_root,
                metadata={"drained_jobs": drained},
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
                self._run_requested_reconciliation(store)
                continue
            except Exception as exc:
                report_reason_failure(
                    exc,
                    event="export_worker_get_error",
                    project_root=self._project_root,
                    metadata=None,
                )
                continue
            try:
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
            finally:
                self._queue.complete(message)
            self._run_requested_reconciliation(store)

    def _run_requested_reconciliation(
        self,
        store: PrivateWorkspaceStore,
    ) -> None:
        if not self._reconciliation_requested.is_set():
            return
        self._reconciliation_requested.clear()
        self._reconcile(store)

    def _process(self, message: JobMessage) -> None:
        thread_id = message.resource_id
        job_id = message.job_id
        write_reason_audit(
            "export_job_dequeued",
            project_root=self._project_root,
            metadata={},
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
            report_reason_failure(
                exc,
                event="export_job_manifest_invalid",
                project_root=self._project_root,
                metadata={},
            )
            return
        if inspection.terminal:
            return
        if inspection.progress_error is not None:
            report_reason_failure(
                inspection.progress_error,
                event="export_job_progress_invalid",
                project_root=self._project_root,
                metadata={},
            )
        write_reason_audit(
            "export_job_composition_started",
            project_root=self._project_root,
            metadata={
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
            report_reason_failure(
                state_error,
                event="export_job_state_persist_failed",
                project_root=self._project_root,
                metadata={},
            )
            return
        attempts = failed_manifest.attempts
        if attempts >= MAX_EXPORT_ATTEMPTS:
            report_reason_failure(
                operation_error,
                event="export_job_failed",
                project_root=self._project_root,
                metadata={"attempts": attempts},
            )
            return
        if self._stopping.is_set() or self._shutdown_requested.is_set():
            return
        backoff = _next_backoff(attempts)
        write_reason_audit(
            "export_job_retry",
            project_root=self._project_root,
            metadata={
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
                name=REASON_OUTPUT_JOB_NAME,
                producer="daemon_retry",
                job_id=job_id,
                resource_id=thread_id,
                payload={"attempt": attempts + 1},
            )
            retry_key = (thread_id, job_id)
            self._retry_job_keys.add(retry_key)
            timer = threading.Timer(
                backoff,
                self._enqueue_retry,
                args=(retry_message,),
            )
            self._timers.append(timer)
            timer.start()

    def _enqueue_retry(self, message: JobMessage) -> None:
        with self._timers_lock:
            self._retry_job_keys.discard(
                (message.resource_id, message.job_id)
            )
        self.enqueue(message)

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
                    report_reason_failure(
                        exc,
                        event="export_reconciliation_skip",
                        project_root=self._project_root,
                        metadata={
                            "thread_id": owner_id,
                            "job_id": job_dir.name,
                        },
                    )
                    continue
                if manifest.status in ("complete", "failed"):
                    continue
                with self._timers_lock:
                    retry_pending = (
                        owner_id,
                        manifest.job_id,
                    ) in self._retry_job_keys
                if retry_pending:
                    continue
                result = self._admit(
                    JobMessage.create(
                        name=REASON_OUTPUT_JOB_NAME,
                        producer="daemon_reconciliation",
                        job_id=manifest.job_id,
                        resource_id=owner_id,
                    )
                )
                if result == "admitted":
                    reconciled += 1
        write_reason_audit(
            "export_queue_reconciled",
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
