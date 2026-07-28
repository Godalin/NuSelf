"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
import os
import socketserver
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import override

from nuself.agent.chat import ChatAgent
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
from nuself.daemon.reason_export import (
    ReasonExportWorker,
    build_reason_export_section_planner,
)
from nuself.daemon.signals import DaemonSignalOwner
from nuself.daemon.transport import (
    read_socket_frame,
    write_stream_frame,
)
from nuself.daemon.types import WorkerHealth
from nuself.daemon.workers import DaemonWorkerSupervisor
from nuself.logs import write_log_event
from nuself.memory.curator import MemoryCurator
from nuself.notification import NotificationAdapter, NotificationDeliveryLoop
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter
from nuself.reason import ReasonScheduler
from nuself.reflection import ReflectionScheduler
from nuself.runtime.context import (
    runtime_context,
)
from nuself.runtime.observability import (
    format_exception_chain,
    report_observed_failure,
    run_observed_best_effort,
)
from nuself.storage import write_text_atomic

DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS = 300
DAEMON_REQUEST_IO_TIMEOUT_SECONDS = 5.0


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


class DaemonState:
    """Mutable daemon state shared by request handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.activity_broker = ActivityBroker()
        self._worker_supervisor = DaemonWorkerSupervisor(
            project_root,
            self.shutdown_requested,
        )
        self.reason_export_worker = ReasonExportWorker(
            project_root,
            self.shutdown_requested,
            self._worker_supervisor,
        )
        self.chat_agent = ChatAgent(
            project_root,
            job_sink=self.reason_export_worker.enqueue,
            section_planner=build_reason_export_section_planner(
                project_root
            ),
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
        self._export_worker_start_lock = threading.Lock()
        for name, thread_name, target in (
            (
                "memory_curator",
                "nuself-memory-curator",
                self._run_background_memory_curator,
            ),
            (
                "reflection_scheduler",
                "nuself-reflection-scheduler",
                self._run_background_reflection_scheduler,
            ),
            (
                "reason_scheduler",
                "nuself-reason-scheduler",
                self._run_background_reason_scheduler,
            ),
            (
                "export_worker",
                "nuself-export-worker",
                self.reason_export_worker.run,
            ),
            (
                "notification_delivery",
                "nuself-notification-delivery",
                self._run_background_notification_delivery,
            ),
        ):
            self._worker_supervisor.register(
                name,
                thread_name=thread_name,
                target=target,
            )
        self._worker_supervisor.seal()

    def worker_health(self) -> tuple[WorkerHealth, ...]:
        """Return a stable snapshot of daemon worker health."""
        return self._worker_supervisor.health()

    def start_background_memory_curator(self) -> None:
        self._worker_supervisor.start("memory_curator")

    def stop_background_memory_curator(self) -> None:
        self._worker_supervisor.join("memory_curator")

    def _run_background_memory_curator(self) -> None:
        self._worker_supervisor.run_scheduled(
            "memory_curator",
            self.memory_curator.run_once,
            interval_seconds=self.memory_curator_interval_seconds,
            started_event="memory_curator_started",
            started_message="memory curator thread started",
            error_event="memory_curator_error",
            error_message="memory curator iteration failed",
        )

    def start_background_reflection_scheduler(self) -> None:
        self._worker_supervisor.start("reflection_scheduler")

    def stop_background_reflection_scheduler(self) -> None:
        self._worker_supervisor.join("reflection_scheduler")

    def _run_background_reflection_scheduler(self) -> None:
        def run_once() -> None:
            if self.reflection_scheduler.should_reflect():
                self.reflection_scheduler.reflect()

        self._worker_supervisor.run_scheduled(
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
            if (
                self._worker_supervisor.snapshot(
                    "reason_scheduler"
                ).state
                != "new"
            ):
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
            self._worker_supervisor.start("reason_scheduler")

    def start_background_export_worker(self) -> None:
        with self._export_worker_start_lock:
            if (
                self._worker_supervisor.snapshot("export_worker").state
                != "new"
            ):
                return
            self.reason_export_worker.prepare()
            self._worker_supervisor.start("export_worker")

    def stop_background_export_worker(self) -> None:
        self.reason_export_worker.stop()
        self._worker_supervisor.join("export_worker")

    def stop_background_reason_scheduler(self) -> None:
        self._worker_supervisor.join("reason_scheduler")

    def _run_background_reason_scheduler(self) -> None:
        def run_once() -> None:
            if self.reason_scheduler is None:
                raise RuntimeError("reason scheduler was not initialized")
            self.reason_scheduler.run_once()

        self._worker_supervisor.run_scheduled(
            "reason_scheduler",
            run_once,
            interval_seconds=self.reason_scheduler_interval_seconds,
            started_event="reason_scheduler_started",
            started_message="reason scheduler thread started",
            error_event="reason_scheduler_error",
            error_message="reason scheduler iteration failed",
        )

    def start_background_notification_delivery(self) -> None:
        self._worker_supervisor.start("notification_delivery")

    def stop_background_notification_delivery(self) -> None:
        self._worker_supervisor.join("notification_delivery")

    def _run_background_notification_delivery(self) -> None:
        self._worker_supervisor.run_scheduled(
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
