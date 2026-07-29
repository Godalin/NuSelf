"""Common lifecycle and observation semantics for daemon workers."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from nuself.clock import utc_now_iso
from nuself.daemon.types import WorkerHealth
from nuself.daemon.operations_audit import report_worker_join_timeout
from nuself.runtime.context import (
    RuntimeContext,
    runtime_context,
    use_runtime_context,
)
from nuself.runtime.event_payloads import (
    RuntimeLogEventPayload,
    RuntimeLogLevel,
)
from nuself.runtime.events import EventPublisher
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import (
    publish_observed_event,
)
from nuself.runtime.workers import (
    OwnedWorker,
    WorkerLifecycleSnapshot,
)


class DaemonWorkerRegistrationError(RuntimeError):
    """Raised when worker registration violates supervisor ownership."""


class DaemonWorkerJoinTimeoutError(RuntimeError):
    """Raised when an owned daemon worker remains alive after join."""


class DaemonWorkerUnexpectedExitError(RuntimeError):
    """Raised internally when a long-lived worker returns before shutdown."""


class DaemonWorkerReadinessError(RuntimeError):
    """Raised when a sealed worker set is not fully running at readiness."""


class DaemonWorkerSupervisor:
    """Own sealed daemon worker registration, health, and execution scopes."""

    def __init__(
        self,
        project_root: Path,
        shutdown_requested: threading.Event,
        event_publisher: EventPublisher,
    ) -> None:
        self._project_root = project_root
        self._shutdown_requested = shutdown_requested
        self._event_publisher = event_publisher
        self._registration_lock = threading.Lock()
        self._health_lock = threading.Lock()
        self._workers: dict[str, OwnedWorker] = {}
        self._health: dict[str, WorkerHealth] = {}
        self._sealed = False

    def register(
        self,
        name: str,
        *,
        thread_name: str,
        target: Callable[[], None],
    ) -> None:
        """Register one worker before sealing the supervisor."""

        with self._registration_lock:
            if self._sealed:
                raise DaemonWorkerRegistrationError(
                    "daemon worker supervisor is sealed"
                )
            if name in self._workers:
                raise DaemonWorkerRegistrationError(
                    f"daemon worker already registered: {name}"
                )
            self._workers[name] = OwnedWorker(
                name=name,
                thread_name=thread_name,
                target=self._supervised_target(name, target),
            )
            self._health[name] = WorkerHealth(name=name)

    def seal(self) -> None:
        """Prevent later worker registration."""

        with self._registration_lock:
            self._sealed = True

    @property
    def registered_names(self) -> tuple[str, ...]:
        with self._registration_lock:
            return tuple(self._workers)

    def start(self, name: str) -> bool:
        self._require_sealed()
        return self._worker(name).start()

    def snapshot(self, name: str) -> WorkerLifecycleSnapshot:
        return self._worker(name).snapshot

    def health(self) -> tuple[WorkerHealth, ...]:
        """Return stable health snapshots in registration order."""

        with self._health_lock:
            recorded = tuple(self._health.items())
        return tuple(
            WorkerHealth(
                name=name,
                alive=self._worker(name).snapshot.alive,
                last_success_at=health.last_success_at,
                last_error=health.last_error,
                consecutive_failures=health.consecutive_failures,
            )
            for name, health in recorded
        )

    def require_all_running(self) -> None:
        """Require every sealed registration to be running and alive."""

        self._require_sealed()
        if self._shutdown_requested.is_set():
            raise DaemonWorkerReadinessError(
                "daemon shutdown was requested before readiness"
            )
        with self._registration_lock:
            workers = tuple(self._workers.items())
        unavailable: list[tuple[str, str]] = []
        for name, worker in workers:
            snapshot = worker.snapshot
            if not snapshot.alive or snapshot.state != "running":
                unavailable.append((name, snapshot.state))
        if not unavailable:
            return
        details = ", ".join(
            f"{name}={state}"
            for name, state in unavailable
        )
        raise DaemonWorkerReadinessError(
            f"daemon workers are not running: {details}"
        )

    def record_failure(self, name: str, exc: BaseException) -> str:
        """Update failure health and return the compact exception chain."""

        chain = diagnostic_exception_chain(exc)
        with self._health_lock:
            previous = self._health_for(name)
            self._health[name] = WorkerHealth(
                name=name,
                alive=True,
                last_success_at=previous.last_success_at,
                last_error=chain,
                consecutive_failures=previous.consecutive_failures + 1,
            )
        return chain

    def run_iteration(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        error_event: str,
        error_message: str,
    ) -> bool:
        """Run one isolated worker iteration and observe expected failure."""

        self._worker(name)
        iteration_context = RuntimeContext(
            job_id=uuid4().hex,
            source=f"daemon.worker.{name}",
        )
        with use_runtime_context(iteration_context):
            try:
                operation()
            except Exception as exc:
                error = self.record_failure(name, exc)
                self._publish_lifecycle_event(
                    name,
                    event="worker.failed",
                    message=error_message,
                    level="error",
                    status="error",
                    error=error,
                    metadata={
                        "operation_event": error_event,
                        "error_type": type(exc).__name__,
                    },
                )
                return False
            self.record_success(name)
            return True

    def run_scheduled(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        interval_seconds: float,
        error_event: str,
        error_message: str,
    ) -> None:
        """Run an observed operation repeatedly until daemon shutdown."""

        self._worker(name)
        while not self._shutdown_requested.wait(interval_seconds):
            self.run_iteration(
                name,
                operation,
                error_event=error_event,
                error_message=error_message,
            )

    def join(self, name: str, timeout: float = 5.0) -> None:
        """Join one worker or report that it remains live."""

        snapshot = self._worker(name).join(timeout=timeout)
        if snapshot.state != "timed_out":
            return
        error = DaemonWorkerJoinTimeoutError(
            f"{name} did not stop within {timeout}s"
        )
        report_worker_join_timeout(
            error,
            project_root=self._project_root,
            worker=name,
            timeout_seconds=timeout,
        )
        raise error

    def _supervised_target(
        self,
        name: str,
        target: Callable[[], None],
    ) -> Callable[[], None]:
        def run() -> None:
            with runtime_context(source=f"daemon.worker.{name}"):
                self._publish_lifecycle_event(
                    name,
                    event="worker.started",
                    message=f"{name} worker started",
                    status="started",
                )
                try:
                    target()
                except Exception as exc:
                    self._record_target_failure(name, exc)
                else:
                    if not self._shutdown_requested.is_set():
                        self._record_target_failure(
                            name,
                            DaemonWorkerUnexpectedExitError(
                                f"{name} returned before daemon shutdown"
                            ),
                        )
                finally:
                    self._publish_lifecycle_event(
                        name,
                        event="worker.stopped",
                        message=f"{name} worker stopped",
                        status="stopped",
                    )

        return run

    def _record_target_failure(
        self,
        name: str,
        error: Exception,
    ) -> None:
        chain = self.record_failure(name, error)
        self._publish_lifecycle_event(
            name,
            event="worker.failed",
            message=f"{name} worker exited unexpectedly",
            level="error",
            status="error",
            error=chain,
            metadata={
                "operation_event": "worker_exited_unexpectedly",
                "error_type": type(error).__name__,
            },
        )

    def record_success(self, name: str) -> None:
        """Record one successful worker operation."""

        with self._health_lock:
            self._health_for(name)
            self._health[name] = WorkerHealth(
                name=name,
                alive=True,
                last_success_at=utc_now_iso(),
            )

    def _publish_lifecycle_event(
        self,
        name: str,
        *,
        event: str,
        message: str,
        level: RuntimeLogLevel = "info",
        status: str,
        error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Publish one lifecycle event without changing worker control flow."""

        self._worker(name)
        event_metadata: dict[str, object] = {"worker": name}
        if metadata is not None:
            event_metadata.update(metadata)
        payload = RuntimeLogEventPayload(
            message=message,
            level=level,
            status=status,
            error=error,
            metadata=event_metadata,
        )
        publish_observed_event(
            self._event_publisher,
            name=event,
            producer="daemon",
            payload=payload.to_mapping(),
            project_root=self._project_root,
            failure_component="daemon",
        )

    def _worker(self, name: str) -> OwnedWorker:
        with self._registration_lock:
            try:
                return self._workers[name]
            except KeyError as exc:
                raise DaemonWorkerRegistrationError(
                    f"unknown daemon worker: {name}"
                ) from exc

    def _health_for(self, name: str) -> WorkerHealth:
        try:
            return self._health[name]
        except KeyError as exc:
            raise DaemonWorkerRegistrationError(
                f"unknown daemon worker: {name}"
            ) from exc

    def _require_sealed(self) -> None:
        with self._registration_lock:
            if not self._sealed:
                raise DaemonWorkerRegistrationError(
                    "daemon worker supervisor is not sealed"
                )
