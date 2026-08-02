"""Durable Reason output workflow executed by the daemon scheduler."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
from nuself.agent.text import TextAgent
from nuself.clock import utc_now_iso
from nuself.llm import LangChainLLMEndpoint
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.reason.output_contracts import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputSection,
)
from nuself.reason.output import ReasonOutputService
from nuself.reason.service import ReasonService
from nuself.reason.audit import (
    report_reason_failure,
    write_reason_audit,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.jobs import JobMessage
from nuself.runtime.job_definitions import JobDefinitionRegistry
from nuself.storage import write_json_atomic
from nuself.workspace import PrivateWorkspaceStore

MAX_EXPORT_ATTEMPTS = 5
EXPORT_RETRY_BASE_SECONDS = 10
EXPORT_RETRY_MAX_SECONDS = 600
ExportTaskSink = Callable[[JobMessage, float], None]

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
class _PendingExportInspection:
    total_chunks: int | str
    progress_error: Exception | None = None


def _inspect_pending_export_job(
    manifest_path: Path,
    *,
    job_id: str,
    thread_id: str,
) -> _PendingExportInspection | None:
    """Decode and correlate one export manifest and optional progress."""

    manifest = _read_export_manifest(manifest_path)
    if manifest.job_id != job_id or manifest.thread_id != thread_id:
        raise ValueError(
            "export manifest identity does not match queue message"
        )
    if manifest.status in ("complete", "failed"):
        return None

    progress_path = manifest_path.with_name(manifest.progress_filename)
    try:
        progress = _read_export_progress(progress_path)
        if progress.job_id != job_id or progress.thread_id != thread_id:
            raise ValueError(
                "export progress identity does not match queue message"
            )
    except FileNotFoundError:
        return _PendingExportInspection(total_chunks="?")
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        return _PendingExportInspection(
            total_chunks="?",
            progress_error=exc,
        )
    return _PendingExportInspection(
        total_chunks=progress.total_chunks,
    )


def _persist_export_failure(
    manifest_path: Path,
    operation_error: Exception,
    *,
    max_attempts: int,
) -> int:
    """Persist one failed composition attempt atomically."""

    manifest = _read_export_manifest(manifest_path)
    attempts = manifest.attempts + 1
    updated = manifest.with_updates(
        status="failed" if attempts >= max_attempts else None,
        attempts=attempts,
        last_error=diagnostic_exception_chain(operation_error),
        last_attempt_at=utc_now_iso(),
    )
    write_json_atomic(manifest_path, updated.to_wire())
    return attempts


def build_reason_export_section_planner(
    project_root: Path,
    *,
    language_preference: str,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    agent: StructuredAgent[ReasonSectionPlanOutput] | None = None,
) -> SectionPlanner:
    """Return an instance-scoped typed-agent section planner."""

    lang = language_preference
    section_agent = (
        agent
        if agent is not None
        else default_structured_agent(
            ReasonSectionPlanOutput,
            project_root=project_root,
            component="reasoning",
            endpoints=langchain_models,
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
        except ValueError as exc:
            report_reason_failure(
                exc,
                event="reason_output_section_plan_fallback",
                project_root=project_root,
                metadata={"mode": mode},
            )
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


class ReasonExportService:
    """Own durable reason-export behavior; scheduling remains daemon-owned."""

    def __init__(
        self,
        project_root: Path,
        *,
        reason_service: ReasonService,
        workspace_store: PrivateWorkspaceStore,
        task_sink: ExportTaskSink,
        language_preference: str,
        text_agent: TextAgent,
        job_definitions: JobDefinitionRegistry | None = None,
    ) -> None:
        self._project_root = project_root
        self._language_preference = language_preference
        self._workspace_store = workspace_store
        self._text_agent = text_agent
        self._job_definitions = (
            job_definitions
            if job_definitions is not None
            else build_reason_job_definition_registry()
        )
        self._task_sink = task_sink
        self._service = ReasonOutputService(
            project_root,
            reason_service=reason_service,
            workspace_store=workspace_store,
        )

    def enqueue(self, message: JobMessage) -> None:
        """Validate and submit one export wake-up to the daemon scheduler."""

        self._job_definitions.validate(message)
        self._task_sink(message, 0.0)

    def process(self, message: JobMessage) -> None:
        """Process one definition-validated scheduler task."""

        self._job_definitions.validate(message)
        thread_id = message.resource_id
        job_id = message.job_id
        write_reason_audit(
            "export_job_dequeued",
            project_root=self._project_root,
            metadata={},
        )

        manifest_path = self._service.job_paths(thread_id, job_id).manifest
        try:
            inspection = _inspect_pending_export_job(
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
            report_reason_failure(
                exc,
                event="export_job_manifest_invalid",
                project_root=self._project_root,
                metadata={},
            )
            return
        if inspection is None:
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
            self._service.compose_with_runner(
                thread_id,
                job_id,
                self._llm_runner,
            )
        except Exception as exc:
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
            attempts = _persist_export_failure(
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
            self._schedule_delayed_reconciliation(thread_id, job_id)
            return
        if attempts >= MAX_EXPORT_ATTEMPTS:
            report_reason_failure(
                operation_error,
                event="export_job_failed",
                project_root=self._project_root,
                metadata={"attempts": attempts},
            )
            return
        backoff = _next_backoff(attempts)
        retry_message = self._job_definitions.create(
            name=REASON_OUTPUT_JOB_NAME,
            producer="daemon_retry",
            job_id=job_id,
            resource_id=thread_id,
            payload={"attempt": attempts + 1},
        )
        retry_metadata: dict[str, object] = {
            "attempts": attempts,
            "next_backoff": backoff,
        }
        try:
            self._task_sink(retry_message, float(backoff))
        except Exception as schedule_error:
            report_reason_failure(
                schedule_error,
                event="export_retry_schedule_failed",
                project_root=self._project_root,
                metadata=retry_metadata,
            )
            self._schedule_delayed_reconciliation(thread_id, job_id)
            return
        write_reason_audit(
            "export_job_retry",
            project_root=self._project_root,
            metadata=retry_metadata,
        )

    def _schedule_delayed_reconciliation(
        self,
        thread_id: str,
        job_id: str,
    ) -> None:
        message = self._job_definitions.create(
            name=REASON_OUTPUT_JOB_NAME,
            producer="daemon_reconciliation",
            job_id=job_id,
            resource_id=thread_id,
        )
        try:
            self._task_sink(message, float(EXPORT_RETRY_BASE_SECONDS))
        except Exception:
            return

    def recover(self) -> None:
        """Rediscover incomplete durable manifests into scheduler wake-ups."""

        reconciled = 0
        for owner_id in self._workspace_store.list_owners():
            jobs_dir = self._workspace_store.paths(owner_id).root / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in sorted(jobs_dir.iterdir()):
                if not job_dir.is_dir():
                    continue
                manifest_path = job_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = _read_export_manifest(manifest_path)
                except (
                    OSError,
                    json.JSONDecodeError,
                    ValueError,
                    KeyError,
                ) as exc:
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
                try:
                    self.enqueue(
                        self._job_definitions.create(
                            name=REASON_OUTPUT_JOB_NAME,
                            producer="daemon_reconciliation",
                            job_id=manifest.job_id,
                            resource_id=owner_id,
                        )
                    )
                except Exception as exc:
                    report_reason_failure(
                        exc,
                        event="export_reconciliation_skip",
                        project_root=self._project_root,
                        metadata={
                            "thread_id": owner_id,
                            "job_id": manifest.job_id,
                        },
                    )
                else:
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
        lang = self._language_preference
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

def _read_export_manifest(path: Path) -> ReasonOutputManifest:
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
