"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
import json
import os
import queue
import socketserver
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast, override

from nuself.agent.chat import ChatAgent
from nuself.clock import utc_now_iso
from nuself.config import (
    ConfigSystem,
    RuntimePaths,
    ensure_runtime_dirs,
    runtime_paths,
)
from nuself.daemon.activity import ActivityBroker
from nuself.daemon.instance import (
    DaemonInstanceLock,
    DaemonInstanceLockContended,
)
from nuself.daemon.protocol import (
    DaemonPeerDisconnected,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
)
from nuself.daemon.request_handlers import handle_request
from nuself.daemon.signals import DaemonSignalOwner
from nuself.daemon.transport import (
    read_socket_frame,
    write_stream_frame,
)
from nuself.daemon.types import WorkerHealth
from nuself.llm import ChatMessage, default_llm
from nuself.logs import write_log_event
from nuself.memory.curator import MemoryCurator
from nuself.notification import NotificationAdapter, NotificationDeliveryLoop
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter
from nuself.reason import ReasonScheduler
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputSection,
    ReasonOutputService,
)
from nuself.reflection import ReflectionScheduler
from nuself.runtime.context import runtime_context
from nuself.runtime.jobs import JobMessage
from nuself.runtime.observability import (
    format_exception_chain,
    report_observed_failure,
    run_observed_best_effort,
)
from nuself.runtime.workers import OwnedWorker
from nuself.storage import write_json_atomic, write_text_atomic
from nuself.workspace import PrivateWorkspaceStore

DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS = 300
DAEMON_REQUEST_IO_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ExportJobInspection:
    manifest: ReasonOutputManifest
    total_chunks: int | str
    progress_error: Exception | None = None

    @property
    def terminal(self) -> bool:
        return self.manifest.status in ("complete", "failed")


@dataclass(frozen=True)
class DaemonCleanupFailure:
    """One named daemon cleanup step that failed."""

    step: str
    error: Exception


class DaemonLifecycleError(RuntimeError):
    """Raised after daemon lifecycle cleanup retains one or more failures."""

    def __init__(
        self,
        failures: tuple[DaemonCleanupFailure, ...],
        *,
        primary_error: BaseException | None = None,
    ) -> None:
        super().__init__(
            f"daemon lifecycle cleanup failed in {len(failures)} step(s)"
        )
        self.failures = failures
        self.primary_error = primary_error


class DaemonWorkerJoinTimeoutError(RuntimeError):
    """Raised when an owned daemon worker remains alive after join."""


def _run_cleanup_steps(
    steps: Sequence[tuple[str, Callable[[], object]]],
) -> tuple[DaemonCleanupFailure, ...]:
    failures: list[DaemonCleanupFailure] = []
    for name, operation in steps:
        try:
            operation()
        except Exception as exc:
            failures.append(DaemonCleanupFailure(name, exc))
    return tuple(failures)


def _finish_daemon_lifecycle(
    *,
    project_root: Path,
    primary_error: BaseException | None,
    cleanup_failures: tuple[DaemonCleanupFailure, ...],
) -> None:
    if cleanup_failures:
        lifecycle_error = DaemonLifecycleError(
            cleanup_failures,
            primary_error=primary_error,
        )
        report_observed_failure(
            lifecycle_error,
            component="daemon",
            event="shutdown_cleanup_failed",
            message="Daemon lifecycle cleanup failed",
            project_root=project_root,
            metadata={
                "steps": [failure.step for failure in cleanup_failures],
                "primary_failed": primary_error is not None,
            },
            level="error",
            status="error",
        )
        if primary_error is not None:
            raise lifecycle_error from primary_error
        raise lifecycle_error
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)


def _read_json_object(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], raw)


def _read_export_manifest(path: Path) -> ReasonOutputManifest:
    return ReasonOutputManifest.from_wire(_read_json_object(path))


def _read_export_progress(path: Path) -> ReasonOutputProgress:
    return ReasonOutputProgress.from_wire(_read_json_object(path))


def _inspect_export_job(
    manifest_path: Path,
    *,
    job_id: str,
    thread_id: str,
) -> ExportJobInspection:
    manifest = _read_export_manifest(manifest_path)
    if manifest.job_id != job_id or manifest.thread_id != thread_id:
        raise ValueError("export manifest identity does not match queue message")
    if manifest.status in ("complete", "failed"):
        return ExportJobInspection(manifest=manifest, total_chunks="?")

    progress_path = manifest_path.with_name(manifest.progress_filename)
    try:
        progress = _read_export_progress(progress_path)
        if progress.job_id != job_id or progress.thread_id != thread_id:
            raise ValueError("export progress identity does not match queue message")
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


def _persist_export_failure(
    manifest_path: Path,
    operation_error: Exception,
    *,
    max_attempts: int,
) -> ReasonOutputManifest:
    manifest = _read_export_manifest(manifest_path)
    attempts = manifest.attempts + 1
    updated = manifest.with_updates(
        status="failed" if attempts >= max_attempts else None,
        attempts=attempts,
        last_error=format_exception_chain(operation_error),
        last_attempt_at=utc_now_iso(),
    )
    write_json_atomic(manifest_path, updated.to_wire())
    return updated


# Export chunk runner protocol intentionally omitted; inline runner typing used.


def _llm_section_planner(project_root: Path) -> Callable[[ReasoningThread, Sequence[ReasoningStep], str], tuple[ReasonOutputSection, ...]]:
    """Return an instance-scoped LLM section planner for chat export tools."""
    lang = ConfigSystem.load(project_root=project_root).chat.language_preference

    def planner(thread: ReasoningThread, steps: Sequence[ReasoningStep], mode: str) -> tuple[ReasonOutputSection, ...]:
        step_lines: list[str] = []
        for i, step in enumerate(steps):
            step_lines.append(f"  {i}. summary: {step.summary}")
            if step.output:
                step_lines.append(f"     output: {step.output[:200]}")
            elif step.delta:
                step_lines.append(f"     delta: {step.delta[:200]}")
        steps_text = "\n".join(step_lines)

        prompt = (
            f"You are planning a {mode} for thread '{thread.topic}'. "
            f"Write in {lang}.\n\n"
            "Organize the following reason steps into 2–8 chapters.\n"
            "For each chapter provide:\n"
            f'- "title" — a descriptive chapter title\n'
            f'- "focus" — what this chapter should cover\n'
            f'- "step_start" — index of the first step (0-based)\n'
            f'- "step_end" — index of the last step (inclusive)\n\n'
            "Return ONLY a valid JSON array (no markdown, no explanation):\n"
            '[{"title": "...", "focus": "...", "step_start": 0, "step_end": 2}, ...]\n\n'
            f"Steps:\n{steps_text}"
        )

        llm = default_llm(project_root)
        raw = llm.complete([ChatMessage(role="user", content=prompt)])

        import json
        try:
            data: list[object] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = []

        sections: list[ReasonOutputSection] = []
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            e = cast(dict[str, object], entry)
            title = str(e.get("title", f"{mode.title()} {i+1}"))
            focus = str(e.get("focus", ""))
            raw_start = e.get("step_start", 0)
            raw_end = e.get("step_end", 0)
            step_start = int(raw_start) if isinstance(raw_start, (int, float, str)) else 0
            step_end = int(raw_end) if isinstance(raw_end, (int, float, str)) else 0
            step_ids = tuple(steps[j].id for j in range(step_start, step_end + 1) if 0 <= j < len(steps))
            sections.append(ReasonOutputSection(
                index=i,
                title=title,
                focus=focus,
                step_ids=step_ids,
                source_start_index=step_start,
                source_end_index=step_end,
                summary=focus[:80] if focus else title[:80],
            ))

        if not sections:
            from nuself.reason.output import plan_sections as fallback_plan
            return fallback_plan(thread, list(steps), mode=mode)

        return tuple(sections)

    return planner


class DaemonState:
    """Mutable daemon state shared by request handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.activity_broker = ActivityBroker()
        self._export_queue: queue.SimpleQueue[JobMessage] = queue.SimpleQueue()
        self.chat_agent = ChatAgent(
            project_root,
            job_sink=self._export_queue.put,
            section_planner=_llm_section_planner(project_root),
        )
        
        config = ConfigSystem.load(project_root=project_root)
        
        self.memory_curator = MemoryCurator(project_root)
        self.memory_curator_interval_seconds: float = config.daemon.memory_curator.interval_seconds
        
        self.reflection_scheduler = ReflectionScheduler(project_root)
        self.reflection_check_interval_seconds: float = config.daemon.reflection_scheduler.check_interval_seconds
        
        adapters: list[NotificationAdapter] = []
        if config.email.enabled:
            adapters.append(EmailNotificationAdapter(project_root))
        if config.macos_notification.enabled:
            adapters.append(MacOSNotificationAdapter(project_root))
        self.notification_delivery_loop = NotificationDeliveryLoop(
            project_root,
            adapters=adapters if adapters else None,
        )
        self.notification_delivery_interval_seconds = config.daemon.notification_delivery.interval_seconds

        self.reason_scheduler: ReasonScheduler | None = None
        self.reason_scheduler_interval_seconds = config.daemon.reason_scheduler.interval_seconds
        self._reason_scheduler_start_lock = threading.Lock()
        self._export_timers: list[threading.Timer] = []
        self._export_timers_lock = threading.Lock()
        self._export_worker_start_lock = threading.Lock()
        self._export_store: PrivateWorkspaceStore | None = None
        self._export_output_service: ReasonOutputService | None = None
        self._worker_health_lock = threading.Lock()
        self._worker_health: dict[str, WorkerHealth] = {
            name: WorkerHealth(name=name)
            for name in (
                "memory_curator",
                "reflection_scheduler",
                "reason_scheduler",
                "export_worker",
                "notification_delivery",
            )
        }
        self._workers: dict[str, OwnedWorker] = {
            "memory_curator": OwnedWorker(
                name="memory_curator",
                thread_name="nuself-memory-curator",
                target=self._supervised_worker_target(
                    "memory_curator",
                    self._run_background_memory_curator,
                ),
            ),
            "reflection_scheduler": OwnedWorker(
                name="reflection_scheduler",
                thread_name="nuself-reflection-scheduler",
                target=self._supervised_worker_target(
                    "reflection_scheduler",
                    self._run_background_reflection_scheduler,
                ),
            ),
            "reason_scheduler": OwnedWorker(
                name="reason_scheduler",
                thread_name="nuself-reason-scheduler",
                target=self._supervised_worker_target(
                    "reason_scheduler",
                    self._run_background_reason_scheduler,
                ),
            ),
            "export_worker": OwnedWorker(
                name="export_worker",
                thread_name="nuself-export-worker",
                target=self._supervised_worker_target(
                    "export_worker",
                    self._run_background_export_worker,
                ),
            ),
            "notification_delivery": OwnedWorker(
                name="notification_delivery",
                thread_name="nuself-notification-delivery",
                target=self._supervised_worker_target(
                    "notification_delivery",
                    self._run_background_notification_delivery,
                ),
            ),
        }

    def _supervised_worker_target(
        self,
        name: str,
        target: Callable[[], None],
    ) -> Callable[[], None]:
        def run() -> None:
            with runtime_context(source=f"daemon.worker.{name}"):
                try:
                    target()
                except Exception as exc:
                    self._record_worker_failure(name, exc)
                    report_observed_failure(
                        exc,
                        component="daemon",
                        event="worker_exited_unexpectedly",
                        message=f"{name} worker exited unexpectedly",
                        project_root=self.project_root,
                        metadata={"worker": name},
                        level="error",
                        status="error",
                    )

        return run

    def worker_health(self) -> tuple[WorkerHealth, ...]:
        """Return a stable snapshot of daemon worker health."""
        with self._worker_health_lock:
            snapshots: list[WorkerHealth] = []
            for name, health in self._worker_health.items():
                lifecycle = self._workers[name].snapshot
                snapshots.append(
                    WorkerHealth(
                        name=name,
                        alive=lifecycle.alive,
                        last_success_at=health.last_success_at,
                        last_error=health.last_error,
                        consecutive_failures=health.consecutive_failures,
                    )
                )
            return tuple(snapshots)

    def _record_worker_success(self, name: str) -> None:
        with self._worker_health_lock:
            self._worker_health[name] = WorkerHealth(
                name=name,
                alive=True,
                last_success_at=utc_now_iso(),
            )

    def _record_worker_failure(self, name: str, exc: BaseException) -> str:
        chain = format_exception_chain(exc)
        with self._worker_health_lock:
            previous = self._worker_health[name]
            self._worker_health[name] = WorkerHealth(
                name=name,
                alive=True,
                last_success_at=previous.last_success_at,
                last_error=chain,
                consecutive_failures=previous.consecutive_failures + 1,
            )
        return chain

    def _write_worker_started(
        self,
        name: str,
        *,
        event: str,
        message: str,
    ) -> None:
        run_observed_best_effort(
            lambda: write_log_event(
                "daemon",
                event,
                message,
                project_root=self.project_root,
                level="info",
                status="started",
                metadata={"worker": name},
            ),
            component="daemon",
            event="worker_start_log_failed",
            message=f"Could not record {name} worker start",
            project_root=self.project_root,
            metadata={"worker": name, "start_event": event},
        )

    def _run_worker_iteration(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        error_event: str,
        error_message: str,
    ) -> bool:
        try:
            operation()
        except Exception as exc:
            self._record_worker_failure(name, exc)
            report_observed_failure(
                exc,
                component="daemon",
                event=error_event,
                message=error_message,
                project_root=self.project_root,
                metadata={"worker": name},
                level="error",
                status="error",
            )
            return False
        self._record_worker_success(name)
        return True

    def _run_scheduled_worker(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        interval_seconds: float,
        started_event: str,
        started_message: str,
        error_event: str,
        error_message: str,
    ) -> None:
        self._write_worker_started(
            name,
            event=started_event,
            message=started_message,
        )
        while not self.shutdown_requested.wait(interval_seconds):
            self._run_worker_iteration(
                name,
                operation,
                error_event=error_event,
                error_message=error_message,
            )

    def start_background_memory_curator(self) -> None:
        self._workers["memory_curator"].start()

    def _join_worker(self, name: str, timeout: float = 5.0) -> None:
        snapshot = self._workers[name].join(timeout=timeout)
        if snapshot.state == "timed_out":
            error = DaemonWorkerJoinTimeoutError(
                f"{name} did not stop within {timeout}s"
            )
            report_observed_failure(
                error,
                component="daemon",
                event="thread_timeout",
                message=f"{name} did not stop within {timeout}s",
                project_root=self.project_root,
                level="warning",
                status="timed_out",
                metadata={
                    "worker": name,
                    "timeout_seconds": timeout,
                    "lifecycle_state": snapshot.state,
                },
            )
            raise error

    def stop_background_memory_curator(self) -> None:
        self._join_worker("memory_curator")

    def _run_background_memory_curator(self) -> None:
        self._run_scheduled_worker(
            "memory_curator",
            self.memory_curator.run_once,
            interval_seconds=self.memory_curator_interval_seconds,
            started_event="memory_curator_started",
            started_message="memory curator thread started",
            error_event="memory_curator_error",
            error_message="memory curator iteration failed",
        )

    def start_background_reflection_scheduler(self) -> None:
        self._workers["reflection_scheduler"].start()

    def stop_background_reflection_scheduler(self) -> None:
        self._join_worker("reflection_scheduler")

    def _run_background_reflection_scheduler(self) -> None:
        def run_once() -> None:
            if self.reflection_scheduler.should_reflect():
                self.reflection_scheduler.reflect()

        self._run_scheduled_worker(
            "reflection_scheduler",
            run_once,
            interval_seconds=self.reflection_check_interval_seconds,
            started_event="reflection_scheduler_started",
            started_message="reflection scheduler thread started",
            error_event="reflection_scheduler_error",
            error_message="reflection scheduler iteration failed",
        )

    def start_background_reason_scheduler(self) -> None:
        with self._reason_scheduler_start_lock:
            worker = self._workers["reason_scheduler"]
            if worker.snapshot.state != "new":
                return
            tools_dict = getattr(self.chat_agent, "_tools", None)
            readonly_tools = (
                [t for t in tools_dict.values() if "readonly" in (t.tags or [])]
                if tools_dict else None
            )
            lc_models = getattr(self.chat_agent, "_langchain_models", None)
            self.reason_scheduler = ReasonScheduler(
                self.project_root,
                interval_seconds=self.reason_scheduler_interval_seconds,
                readonly_tools=readonly_tools,
                langchain_models=lc_models,
            )
            worker.start()

    def start_background_export_worker(self) -> None:
        with self._export_worker_start_lock:
            worker = self._workers["export_worker"]
            if worker.snapshot.state != "new":
                return
            self._export_store = PrivateWorkspaceStore(
                self.project_root,
                scope="reason",
            )
            self._export_output_service = ReasonOutputService(
                self.project_root
            )
            worker.start()

    def stop_background_export_worker(self) -> None:
        with self._export_timers_lock:
            for t in self._export_timers:
                t.cancel()
            self._export_timers.clear()
        # Drain remaining queue items (they won't be processed)
        drained = 0
        while not self._export_queue.empty():
            try:
                self._export_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        if drained:
            write_log_event(
                "daemon",
                "export_queue_drained",
                f"Drained {drained} unprocessed export jobs",
                project_root=self.project_root,
                level="warning",
            )
        self._join_worker("export_worker")

    def _run_background_export_worker(self) -> None:
        self._write_worker_started(
            "export_worker",
            event="export_worker_started",
            message="export queue worker thread started",
        )

        store = self._export_store
        service = self._export_output_service
        if store is None or service is None:
            raise RuntimeError(
                "export worker dependencies were not initialized"
            )

        def _llm_runner(
            thread: ReasoningThread,
            manifest: ReasonOutputManifest,
            steps: Sequence[ReasoningStep],
            *,
            section: ReasonOutputSection,
            section_plan: Sequence[ReasonOutputSection],
            index: int,
            total: int,
        ) -> str:
            lang = ConfigSystem.load(project_root=self.project_root).chat.language_preference
            sys = (
                f"You are a writing assistant. Compose a {manifest.mode} in {manifest.output_format} format "
                "from the provided reason steps. "
                f"Write in {lang}. "
                "Produce plain Markdown paragraphs — do NOT include headings or section titles, "
                "they will be added automatically. "
                "Keep terminology and tone consistent across all chunks."
            )
            pieces: list[ChatMessage] = [ChatMessage(role="system", content=sys)]
            body_lines: list[str] = [""]
            body_lines.append(f"Current section: {section.title}")
            body_lines.append(f"Section focus: {section.focus}")
            body_lines.append("")
            body_lines.append("Global section plan:")
            for planned in section_plan:
                marker = " (current)" if planned.index == section.index else ""
                body_lines.append(f"  - {planned.index + 1}. {planned.title}: {planned.focus}{marker}")
            for s in steps:
                body_lines.append("---")
                body_lines.append(f"Step: {s.summary}")
                if s.output:
                    body_lines.append(s.output)
                elif s.delta:
                    body_lines.append(s.delta)
                if s.evidence_refs:
                    body_lines.append("Evidence:")
                    body_lines.extend(f"- {r}" for r in s.evidence_refs)
            user = "\n".join(body_lines)
            pieces.append(ChatMessage(role="user", content=user))
            llm = default_llm(self.project_root)
            return llm.complete(pieces)

        MAX_ATTEMPTS = 5
        BASE_BACKOFF = 10  # seconds
        MAX_BACKOFF = 600  # seconds

        def _next_backoff(attempts: int) -> int:
            return min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (attempts - 1)))

        # --- Startup reconciliation ---
        # Re-enqueue any job whose manifest status is not complete/failed.
        # Also clear stale .lock files from crashed runs.
        reconciled = 0
        for owner_id in store.list_owners():
            jobs_dir = store.paths(owner_id).artifacts / "export" / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in sorted(jobs_dir.iterdir()):
                if not job_dir.is_dir():
                    continue
                # Clear stale lock
                lock_path = job_dir / ".lock"
                if lock_path.exists():
                    lock_path.unlink(missing_ok=True)
                manifest_path = job_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = _read_export_manifest(manifest_path)
                except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
                    self._record_worker_failure("export_worker", exc)
                    write_log_event(
                        "daemon",
                        "export_reconciliation_skip",
                        f"Skipping invalid export manifest for {job_dir.name}",
                        project_root=self.project_root,
                        level="warning",
                        status="error",
                        error=format_exception_chain(exc),
                        metadata={
                            "thread_id": owner_id,
                            "job_id": job_dir.name,
                        },
                    )
                    continue
                if manifest.status in ("complete", "failed"):
                    continue
                self._export_queue.put(
                    JobMessage.create(
                        name="reason.output.export",
                        producer="daemon.reconciliation",
                        job_id=manifest.job_id,
                        resource_id=owner_id,
                    )
                )
                reconciled += 1

        write_log_event(
            "daemon",
            "export_queue_reconciled",
            f"Export queue reconciled on startup; re-enqueued {reconciled} job(s)",
            project_root=self.project_root,
            metadata={"replayed_jobs": reconciled},
        )

        # --- Main event loop ---
        # Block on queue.get() with a 1-second timeout to stay responsive
        # to shutdown_requested. No polling interval needed — events arrive
        # immediately via the in-memory queue.
        while not self.shutdown_requested.is_set():
            try:
                job_message = self._export_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            except Exception as exc:
                write_log_event(
                    "daemon",
                    "export_worker_get_error",
                    f"export queue.get() error: {exc!s}",
                    project_root=self.project_root,
                    level="warning",
                    status="error",
                    error=str(exc),
                )
                continue

            if self.shutdown_requested.is_set():
                break
            if job_message.envelope.name != "reason.output.export":
                write_log_event(
                    "daemon",
                    "export_job_type_ignored",
                    f"Ignored unsupported export job type {job_message.envelope.name}",
                    project_root=self.project_root,
                    level="warning",
                    metadata={"message_id": job_message.envelope.message_id},
                )
                continue
            thread_id = job_message.resource_id
            job_id = job_message.job_id

            write_log_event(
                "daemon",
                "export_job_dequeued",
                f"Processing export job {job_id} for thread {thread_id}",
                project_root=self.project_root,
                metadata={"job_id": job_id, "thread_id": thread_id},
            )

            manifest_path = store.paths(thread_id).artifacts / "export" / "jobs" / job_id / "manifest.json"
            try:
                inspection = _inspect_export_job(
                    manifest_path,
                    job_id=job_id,
                    thread_id=thread_id,
                )
            except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
                self._record_worker_failure("export_worker", exc)
                write_log_event(
                    "daemon",
                    "export_job_manifest_invalid",
                    f"Cannot process export job {job_id}: invalid manifest",
                    project_root=self.project_root,
                    level="error",
                    status="error",
                    error=format_exception_chain(exc),
                    metadata={"job_id": job_id, "thread_id": thread_id},
                )
                continue

            if inspection.terminal:
                continue

            if inspection.progress_error is not None:
                write_log_event(
                    "daemon",
                    "export_job_progress_invalid",
                    f"Ignoring invalid progress for export job {job_id}",
                    project_root=self.project_root,
                    level="warning",
                    status="degraded",
                    error=format_exception_chain(inspection.progress_error),
                    metadata={"job_id": job_id, "thread_id": thread_id},
                )

            write_log_event(
                "daemon",
                "export_job_composition_started",
                f"Composing {inspection.total_chunks} chunk(s) for job {job_id}",
                project_root=self.project_root,
                metadata={
                    "job_id": job_id,
                    "thread_id": thread_id,
                    "chunks": inspection.total_chunks,
                },
            )

            try:
                service.compose_with_runner(thread_id, job_id, _llm_runner)
                self._record_worker_success("export_worker")
            except Exception as exc:
                self._record_worker_failure("export_worker", exc)
                try:
                    failed_manifest = _persist_export_failure(
                        manifest_path,
                        exc,
                        max_attempts=MAX_ATTEMPTS,
                    )
                except Exception as state_exc:
                    write_log_event(
                        "daemon",
                        "export_job_state_persist_failed",
                        f"Could not persist failure state for export job {job_id}",
                        project_root=self.project_root,
                        level="error",
                        status="error",
                        error=format_exception_chain(state_exc),
                        metadata={
                            "job_id": job_id,
                            "thread_id": thread_id,
                            "operation_error": format_exception_chain(exc),
                        },
                    )
                    continue

                attempts = failed_manifest.attempts

                if attempts >= MAX_ATTEMPTS:
                    write_log_event(
                        "daemon",
                        "export_job_failed",
                        f"Export job {job_id} exhausted retries: {exc!s}",
                        project_root=self.project_root,
                        level="error",
                        status="error",
                        error=format_exception_chain(exc),
                        metadata={"job_id": job_id, "thread_id": thread_id, "attempts": attempts},
                    )
                else:
                    backoff = _next_backoff(attempts)
                    write_log_event(
                        "daemon",
                        "export_job_retry",
                        f"Export job {job_id} will retry in {backoff}s (attempt {attempts})",
                        project_root=self.project_root,
                        status="retry",
                        metadata={"job_id": job_id, "thread_id": thread_id, "attempts": attempts, "next_backoff": backoff},
                    )
                    with self._export_timers_lock:
                        # Drop timers that have already fired so the list cannot
                        # grow unbounded over a long-lived daemon with many retries.
                        self._export_timers = [x for x in self._export_timers if x.is_alive()]
                        retry_message = JobMessage.create(
                            name="reason.output.export",
                            producer="daemon.retry",
                            job_id=job_id,
                            resource_id=thread_id,
                            payload={"attempt": attempts + 1},
                        )
                        t = threading.Timer(
                            backoff,
                            self._export_queue.put,
                            args=(retry_message,),
                        )
                        self._export_timers.append(t)
                        t.start()

    def stop_background_reason_scheduler(self) -> None:
        self._join_worker("reason_scheduler")

    def _run_background_reason_scheduler(self) -> None:
        def run_once() -> None:
            if self.reason_scheduler is None:
                raise RuntimeError("reason scheduler was not initialized")
            self.reason_scheduler.run_once()

        self._run_scheduled_worker(
            "reason_scheduler",
            run_once,
            interval_seconds=self.reason_scheduler_interval_seconds,
            started_event="reason_scheduler_started",
            started_message="reason scheduler thread started",
            error_event="reason_scheduler_error",
            error_message="reason scheduler iteration failed",
        )

    def start_background_notification_delivery(self) -> None:
        self._workers["notification_delivery"].start()

    def stop_background_notification_delivery(self) -> None:
        self._join_worker("notification_delivery")

    def _run_background_notification_delivery(self) -> None:
        self._run_scheduled_worker(
            "notification_delivery",
            self.notification_delivery_loop.run_once,
            interval_seconds=self.notification_delivery_interval_seconds,
            started_event="notification_delivery_started",
            started_message="notification delivery thread started",
            error_event="notification_delivery_error",
            error_message="notification delivery iteration failed",
        )


class NuSelfUnixServer(socketserver.ThreadingUnixStreamServer):
    """Unix stream server with typed NuSelf state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, handler: type[socketserver.BaseRequestHandler], state: DaemonState) -> None:
        self.state = state
        super().__init__(socket_path, handler)


class RequestHandler(socketserver.StreamRequestHandler):
    """Handle one JSONL request per client connection."""

    @override
    def handle(self) -> None:
        request_id = "unknown"
        try:
            self.connection.settimeout(
                DAEMON_REQUEST_IO_TIMEOUT_SECONDS
            )
            raw_line = read_socket_frame(self.connection)
        except DaemonPeerDisconnected:
            return
        except ProtocolError as exc:
            response = DaemonResponse.fail(request_id, str(exc))
        except OSError as exc:
            report_observed_failure(
                exc,
                component="daemon",
                event="request_transport_failed",
                message="Daemon request transport failed",
                project_root=self._request_project_root(),
                metadata=None,
                level="warning",
                status="error",
            )
            response = DaemonResponse.fail(
                request_id,
                format_exception_chain(exc),
            )
        else:
            try:
                daemon_request = DaemonRequest.from_json_line(raw_line)
                request_id = daemon_request.request_id
                response = handle_request(
                    daemon_request,
                    self._daemon_state(),
                )
            except ProtocolError as exc:
                response = DaemonResponse.fail(request_id, str(exc))
            except Exception as exc:
                chain = format_exception_chain(exc)
                with runtime_context(
                    request_id=request_id,
                    source="daemon",
                ):
                    report_observed_failure(
                        exc,
                        component="daemon",
                        event="request_failed",
                        message="Daemon request handling failed",
                        project_root=self._request_project_root(),
                        metadata=None,
                        level="error",
                        status="error",
                    )
                response = DaemonResponse.fail(request_id, chain)

        try:
            write_stream_frame(
                self.wfile,
                response.to_json_line(),
            )
        except (OSError, ProtocolError) as exc:
            context = (
                runtime_context(
                    request_id=request_id,
                    source="daemon",
                )
                if request_id != "unknown"
                else runtime_context(source="daemon")
            )
            with context:
                report_observed_failure(
                    exc,
                    component="daemon",
                    event="response_delivery_failed",
                    message="Daemon response could not be delivered",
                    project_root=self._request_project_root(),
                    metadata=None,
                    level="warning",
                    status="error",
                )

    def _request_project_root(self) -> Path | None:
        try:
            return self._daemon_state().project_root
        except Exception:
            return None

    def _daemon_state(self) -> DaemonState:
        server = self.server
        if not isinstance(server, NuSelfUnixServer):
            raise RuntimeError("unexpected server type")
        return server.state


def run_daemon(project_root: Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    instance_lock = DaemonInstanceLock(
        paths.runtime_dir / "nuself.lock"
    )
    try:
        instance_lock.acquire()
    except DaemonInstanceLockContended as exc:
        write_log_event(
            "daemon",
            "instance_lock_contended",
            "daemon start rejected because this project already has an owner",
            project_root=paths.project_root,
            level="warning",
            status="skipped",
            error=str(exc),
        )
        return 1
    result = 0
    primary_error: BaseException | None = None
    try:
        result = _run_owned_daemon(paths)
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = _run_cleanup_steps(
        (("instance_lock.release", instance_lock.release),)
    )
    _finish_daemon_lifecycle(
        project_root=paths.project_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return result


def _run_owned_daemon(paths: RuntimePaths) -> int:
    """Run the daemon while the caller holds project instance ownership."""

    state: DaemonState | None = None
    signal_owner: DaemonSignalOwner | None = None
    started = False
    primary_error: BaseException | None = None
    try:
        paths.socket_path.unlink(missing_ok=True)
        write_text_atomic(paths.pid_path, f"{os.getpid()}\n")
        state = DaemonState(paths.project_root)
        signal_owner = DaemonSignalOwner(state.shutdown_requested)
        signal_owner.install()

        with NuSelfUnixServer(str(paths.socket_path), RequestHandler, state) as server:
            write_log_event(
                "daemon",
                "started",
                "daemon started",
                project_root=paths.project_root,
            )
            started = True
            state.start_background_memory_curator()
            state.start_background_reflection_scheduler()
            state.start_background_reason_scheduler()
            state.start_background_export_worker()
            state.start_background_notification_delivery()
            server.timeout = 0.2
            while not state.shutdown_requested.is_set():
                server.handle_request()
    except BaseException as exc:
        primary_error = exc

    cleanup_steps: list[tuple[str, Callable[[], object]]] = []
    if state is not None:
        cleanup_steps.extend(
            (
                ("shutdown.signal", state.shutdown_requested.set),
                (
                    "worker.memory_curator.stop",
                    state.stop_background_memory_curator,
                ),
                (
                    "worker.reflection_scheduler.stop",
                    state.stop_background_reflection_scheduler,
                ),
                (
                    "worker.reason_scheduler.stop",
                    state.stop_background_reason_scheduler,
                ),
                (
                    "worker.export_worker.stop",
                    state.stop_background_export_worker,
                ),
                (
                    "worker.notification_delivery.stop",
                    state.stop_background_notification_delivery,
                ),
            )
        )
    if signal_owner is not None:
        cleanup_steps.append(
            ("signal_handlers.restore", signal_owner.restore)
        )
    from nuself.storage import reset_default_backend

    cleanup_steps.extend(
        (
            (
                "storage.default_backend.reset",
                lambda: reset_default_backend(paths.project_root),
            ),
            ("socket.unlink", lambda: paths.socket_path.unlink(missing_ok=True)),
            ("pid.unlink", lambda: paths.pid_path.unlink(missing_ok=True)),
        )
    )
    cleanup_failures = _run_cleanup_steps(cleanup_steps)
    if started and not cleanup_failures:
        run_observed_best_effort(
            lambda: write_log_event(
                "daemon",
                "stopped",
                "daemon stopped",
                project_root=paths.project_root,
            ),
            component="daemon",
            event="stopped_log_failed",
            message="Could not record daemon stop",
            project_root=paths.project_root,
            metadata=None,
        )
    _finish_daemon_lifecycle(
        project_root=paths.project_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nuself.daemon.server")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_daemon(args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
