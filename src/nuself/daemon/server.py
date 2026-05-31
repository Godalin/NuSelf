"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import queue
import socketserver
import threading
import time
from collections.abc import Sequence
from typing import override

from nuself.agent.chat import ChatAgent
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.output import ReasonOutputManifest, ReasonOutputSection
from nuself.reason.output import set_enqueue_callback
from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.config import ConfigSystem
from nuself.daemon.protocol import DaemonRequest, DaemonResponse, JsonValue, ProtocolError
from nuself.logs import log_context, write_log_event
from nuself.memory.curator import MemoryCurator, MemoryCuratorResult
from nuself.notification import NotificationAdapter, NotificationDeliveryLoop
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter
from nuself.reason import ReasonScheduler
from nuself.reflection import ReflectionScheduler


DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS = 300


def _format_exception_chain(exc: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = str(current)
        if message:
            messages.append(message)
        current = current.__cause__ or current.__context__
    return " <- ".join(messages) if messages else exc.__class__.__name__


# Export chunk runner protocol intentionally omitted; inline runner typing used.


class DaemonState:
    """Mutable daemon state shared by request handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.chat_agent = ChatAgent(project_root)
        
        config = ConfigSystem.load(project_root=project_root)
        
        self.memory_curator = MemoryCurator(project_root)
        self.memory_curator_interval_seconds = config.daemon.memory_curator.interval_seconds
        self._memory_curator_thread: threading.Thread | None = None
        
        self.reflection_scheduler = ReflectionScheduler(project_root)
        self.reflection_check_interval_seconds: float = config.daemon.reflection_scheduler.check_interval_seconds
        self._reflection_scheduler_thread: threading.Thread | None = None
        
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
        self._notification_delivery_thread: threading.Thread | None = None

        self.reason_scheduler: ReasonScheduler | None = None
        self.reason_scheduler_interval_seconds = config.daemon.reason_scheduler.interval_seconds
        self._reason_scheduler_thread: threading.Thread | None = None
        self._export_queue: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self._export_worker_thread: threading.Thread | None = None

    def start_background_memory_curator(self) -> None:
        if self._memory_curator_thread is not None:
            return
        self._memory_curator_thread = threading.Thread(
            target=self._run_background_memory_curator,
            name="nuself-memory-curator",
            daemon=True,
        )
        self._memory_curator_thread.start()

    def stop_background_memory_curator(self) -> None:
        if self._memory_curator_thread is not None:
            self._memory_curator_thread.join(timeout=1.0)

    def _run_background_memory_curator(self) -> None:
        from nuself.logs import write_log_event
        
        write_log_event(
            "daemon",
            "memory_curator_started",
            "memory curator thread started",
            project_root=self.project_root,
            level="info",
            status="started"
        )
        
        while not self.shutdown_requested.wait(self.memory_curator_interval_seconds):
            try:
                self.memory_curator.run_once()
            except RuntimeError:
                continue

    def start_background_reflection_scheduler(self) -> None:
        if self._reflection_scheduler_thread is not None:
            return
        self._reflection_scheduler_thread = threading.Thread(
            target=self._run_background_reflection_scheduler,
            name="nuself-reflection-scheduler",
            daemon=True,
        )
        self._reflection_scheduler_thread.start()

    def stop_background_reflection_scheduler(self) -> None:
        if self._reflection_scheduler_thread is not None:
            self._reflection_scheduler_thread.join(timeout=1.0)

    def _run_background_reflection_scheduler(self) -> None:
        from nuself.logs import write_log_event
        
        write_log_event(
            "daemon",
            "reflection_scheduler_started",
            "reflection scheduler thread started",
            project_root=self.project_root,
            level="info",
            status="started"
        )
        
        while not self.shutdown_requested.wait(self.reflection_check_interval_seconds):
            try:
                should_reflect = self.reflection_scheduler.should_reflect()
                if should_reflect:
                    self.reflection_scheduler.reflect()
            except RuntimeError as e:
                write_log_event(
                    "daemon",
                    "reflection_scheduler_error",
                    f"reflection scheduler error: {str(e)}",
                    project_root=self.project_root,
                    level="error",
                    status="error",
                    error=str(e)
                )
                continue

    def start_background_reason_scheduler(self) -> None:
        if self._reason_scheduler_thread is not None:
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
        self._reason_scheduler_thread = threading.Thread(
            target=self._run_background_reason_scheduler,
            name="nuself-reason-scheduler",
            daemon=True,
        )
        self._reason_scheduler_thread.start()

    def start_background_export_worker(self) -> None:
        if self._export_worker_thread is not None:
            return
        # Register the module-level callback so all ReasonOutputService
        # instances push to this process's in-memory queue.
        set_enqueue_callback(lambda tid, jid: self._export_queue.put((tid, jid)))
        self._export_worker_thread = threading.Thread(
            target=self._run_background_export_worker,
            name="nuself-export-worker",
            daemon=True,
        )
        self._export_worker_thread.start()

    def stop_background_export_worker(self) -> None:
        if self._export_worker_thread is not None:
            self._export_worker_thread.join(timeout=1.0)

    def _run_background_export_worker(self) -> None:
        from datetime import UTC, datetime
        from nuself.logs import write_log_event
        from nuself.reason.output import ReasonOutputService
        from nuself.workspace import PrivateWorkspaceStore
        from nuself.llm import default_llm, ChatMessage

        write_log_event(
            "daemon",
            "export_worker_started",
            "export queue worker thread started",
            project_root=self.project_root,
            status="started",
        )

        store = PrivateWorkspaceStore(self.project_root, scope="reason")
        service = ReasonOutputService(self.project_root)

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
            section_title = section.title
            section_focus = section.focus
            section_steps = section.step_ids
            sys = (
                f"You are a writing assistant. Compose a {manifest.mode} in {manifest.output_format} format "
                "from the provided reason steps. Produce Markdown suitable for direct display. "
                "Follow the export plan exactly. Keep chapter names, terminology, and ordering stable across chunks."
            )
            pieces: list[ChatMessage] = [ChatMessage(role="system", content=sys)]
            body_lines: list[str] = [f"Chunk {index + 1}/{total}: {section_title}"]
            body_lines.append(f"Section focus: {section_focus}")
            body_lines.append(f"Section step ids: {', '.join(str(step_id) for step_id in section_steps)}")
            body_lines.append("")
            body_lines.append("Global section plan:")
            for planned in section_plan:
                planned_title = planned.title
                planned_focus = planned.focus
                planned_index = planned.index
                marker = " (current)" if planned_index == index else ""
                body_lines.append(f"- {planned_index + 1}. {planned_title}: {planned_focus}{marker}")
            body_lines.append("")
            body_lines.append("Compose the current section using its title as the heading and keeping the rest of the plan in view.")
            body_lines.append("")
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
                    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    write_log_event(
                        "daemon",
                        "export_reconciliation_skip",
                        f"Skipping corrupted manifest: {manifest_path}",
                        project_root=self.project_root,
                        level="warning",
                        status="error",
                        metadata={"owner_id": owner_id, "path": str(manifest_path)},
                    )
                    continue
                status = raw.get("status")
                if status in ("complete", "failed"):
                    continue
                job_id = raw.get("job_id", job_dir.name)
                if isinstance(job_id, str):
                    self._export_queue.put((owner_id, job_id))
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
                thread_id, job_id = self._export_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            except Exception as exc:
                write_log_event(
                    "daemon",
                    "export_worker_get_error",
                    f"export queue.get() error: {str(exc)}",
                    project_root=self.project_root,
                    level="warning",
                    status="error",
                    error=str(exc),
                )
                continue

            if self.shutdown_requested.is_set():
                break

            manifest_path = store.paths(thread_id).artifacts / "export" / "jobs" / job_id / "manifest.json"
            try:
                if manifest_path.exists():
                    try:
                        raw: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        raw = {}
                    if raw.get("status") == "complete":
                        continue

                service.compose_with_runner(thread_id, job_id, _llm_runner)
            except Exception as exc:
                from nuself.reason.output import ReasonOutputManifest, write_json_atomic

                # Persist attempts + error info on every failure using the
                # typed manifest model, so crash recovery preserves counters.
                attempts = 1
                now_iso = datetime.now(UTC).isoformat()
                if manifest_path.exists():
                    try:
                        raw: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = ReasonOutputManifest.from_wire(raw)
                        raw_attempts = manifest.attempts
                        attempts = raw_attempts + 1
                        if attempts >= MAX_ATTEMPTS:
                            updated = manifest.with_updates(
                                status="failed", attempts=attempts,
                                last_error=str(exc), last_attempt_at=now_iso,
                            )
                        else:
                            updated = manifest.with_updates(
                                attempts=attempts,
                                last_error=str(exc), last_attempt_at=now_iso,
                            )
                        write_json_atomic(manifest_path, updated.to_wire())
                    except Exception:
                        pass

                if attempts >= MAX_ATTEMPTS:
                    write_log_event(
                        "daemon",
                        "export_job_failed",
                        f"Export job {job_id} exhausted retries: {str(exc)}",
                        project_root=self.project_root,
                        level="error",
                        status="error",
                        error=str(exc),
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
                    threading.Timer(backoff, self._export_queue.put, args=((thread_id, job_id),)).start()

    def stop_background_reason_scheduler(self) -> None:
        if self._reason_scheduler_thread is not None:
            self._reason_scheduler_thread.join(timeout=1.0)

    def _run_background_reason_scheduler(self) -> None:
        from nuself.logs import write_log_event

        write_log_event(
            "daemon",
            "reason_scheduler_started",
            "reason scheduler thread started",
            project_root=self.project_root,
            level="info",
            status="started"
        )

        while not self.shutdown_requested.wait(self.reason_scheduler_interval_seconds):
            try:
                if self.reason_scheduler is not None:
                    self.reason_scheduler.run_once()
            except Exception as e:
                write_log_event(
                    "daemon",
                    "reason_scheduler_error",
                    f"reason scheduler error: {str(e)}",
                    project_root=self.project_root,
                    level="error",
                    status="error",
                    error=str(e),
                )
                continue

    def start_background_notification_delivery(self) -> None:
        if self._notification_delivery_thread is not None:
            return
        self._notification_delivery_thread = threading.Thread(
            target=self._run_background_notification_delivery,
            name="nuself-notification-delivery",
            daemon=True,
        )
        self._notification_delivery_thread.start()

    def stop_background_notification_delivery(self) -> None:
        if self._notification_delivery_thread is not None:
            self._notification_delivery_thread.join(timeout=1.0)

    def _run_background_notification_delivery(self) -> None:
        from nuself.logs import write_log_event
        
        write_log_event(
            "daemon",
            "notification_delivery_started",
            "notification delivery thread started",
            project_root=self.project_root,
            level="info",
            status="started"
        )
        
        while not self.shutdown_requested.wait(self.notification_delivery_interval_seconds):
            try:
                self.notification_delivery_loop.run_once()
            except RuntimeError:
                continue


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
        raw_line = self.rfile.readline()
        request_id = "unknown"
        try:
            daemon_request = DaemonRequest.from_json_line(raw_line)
            request_id = daemon_request.request_id
            response = handle_request(daemon_request, self._daemon_state())
        except ProtocolError as exc:
            response = DaemonResponse.fail(request_id, str(exc))
        self.wfile.write(response.to_json_line())

    def _daemon_state(self) -> DaemonState:
        server = self.server
        if not isinstance(server, NuSelfUnixServer):
            raise RuntimeError("unexpected server type")
        return server.state


def handle_request(request: DaemonRequest, state: DaemonState) -> DaemonResponse:
    """Handle a typed daemon request."""

    if request.type == "ping":
        return DaemonResponse.ok(request, {"message": "pong"})
    if request.type == "echo":
        return DaemonResponse.ok(request, request.payload)
    if request.type == "chat":
        message = request.payload.get("message")
        if not isinstance(message, str):
            write_log_event(
                "daemon",
                "request_failed",
                "chat request rejected",
                project_root=state.project_root,
                level="warning",
                request_id=request.request_id,
                status="error",
                error="chat request requires string payload field 'message'",
            )
            return DaemonResponse.fail(request.request_id, "chat request requires string payload field 'message'")
        thread_id_raw = request.payload.get("thread_id")
        thread_id = thread_id_raw if isinstance(thread_id_raw, str) else "default"
        turn_id_raw = request.payload.get("turn_id")
        turn_id = turn_id_raw if isinstance(turn_id_raw, str) else None
        started_at = time.monotonic()
        with log_context(request_id=request.request_id, thread_id=thread_id, turn_id=turn_id, source="daemon"):
            try:
                result = state.chat_agent.respond(message, thread_id=thread_id, turn_id=turn_id)
                memory_update = _run_memory_curator_once(state.memory_curator, source_trace_id=result.trace_id)
            except RuntimeError as exc:
                error_detail = _format_exception_chain(exc)
                write_log_event(
                    "daemon",
                    "chat_turn_failed",
                    "daemon chat turn failed",
                    project_root=state.project_root,
                    level="error",
                    status="error",
                    error=error_detail,
                )
                return DaemonResponse.fail(request.request_id, error_detail)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        payload: dict[str, JsonValue] = {
            "answer": result.answer,
            "reply": result.reply,
            "thread_id": result.thread_id,
            "evidence_references": list(result.evidence_references),
            "epistemic_status": result.epistemic_status,
        }
        if result.confidence is not None:
            payload["confidence"] = result.confidence
        if memory_update is not None and memory_update.changed:
            payload["memory_update"] = memory_update.summary()
        with log_context(request_id=request.request_id, thread_id=result.thread_id, turn_id=turn_id, source="daemon"):
            write_log_event(
                "daemon",
                "chat_turn_completed",
                "daemon chat turn completed",
                project_root=state.project_root,
                duration_ms=duration_ms,
                status="ok",
                metadata={
                    "evidence_references": len(result.evidence_references),
                    "memory_changed": memory_update.changed if memory_update is not None else False,
                },
            )
        return DaemonResponse.ok(request, payload)
    if request.type == "shutdown":
        write_log_event(
            "daemon",
            "shutdown_requested",
            "daemon shutdown requested",
            project_root=state.project_root,
            request_id=request.request_id,
        )
        state.shutdown_requested.set()
        return DaemonResponse.ok(request, {"message": "shutdown requested"})
    return DaemonResponse.fail(request.request_id, f"unsupported request type: {request.type}")


def _run_memory_curator_once(memory_curator: MemoryCurator, *, source_trace_id: str | None = None) -> MemoryCuratorResult | None:
    try:
        return memory_curator.run_once(source_trace_id=source_trace_id)
    except RuntimeError:
        return None


def run_daemon(project_root: Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    if paths.socket_path.exists():
        paths.socket_path.unlink()
    paths.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    state = DaemonState(paths.project_root)
    try:
        write_log_event("daemon", "started", "daemon started", project_root=paths.project_root)
        state.start_background_memory_curator()
        state.start_background_reflection_scheduler()
        state.start_background_reason_scheduler()
        state.start_background_export_worker()
        state.start_background_notification_delivery()
        with NuSelfUnixServer(str(paths.socket_path), RequestHandler, state) as server:
            server.timeout = 0.2
            while not state.shutdown_requested.is_set():
                server.handle_request()
    finally:
        write_log_event("daemon", "stopped", "daemon stopped", project_root=paths.project_root)
        state.stop_background_memory_curator()
        state.stop_background_reflection_scheduler()
        state.stop_background_reason_scheduler()
        state.stop_background_export_worker()
        state.stop_background_notification_delivery()
        if paths.socket_path.exists():
            paths.socket_path.unlink()
        if paths.pid_path.exists():
            paths.pid_path.unlink()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nuself.daemon.server")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_daemon(args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
