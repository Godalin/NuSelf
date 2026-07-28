"""Common lifecycle and observation semantics for daemon workers."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from nuself.clock import utc_now_iso
from nuself.daemon.types import WorkerHealth
from nuself.logs import write_log_event
from nuself.runtime.context import (
    RuntimeContext,
    runtime_context,
    use_runtime_context,
)
from nuself.runtime.observability import (
    format_exception_chain,
    report_observed_failure,
    run_observed_best_effort,
)
from nuself.runtime.workers import (
    OwnedWorker,
    WorkerLifecycleSnapshot,
)


class DaemonWorkerRegistrationError(RuntimeError):
    """Raised when worker registration violates supervisor ownership."""


class DaemonWorkerJoinTimeoutError(RuntimeError):
    """Raised when an owned daemon worker remains alive after join."""


class DaemonWorkerSupervisor:
    """Own sealed daemon worker registration, health, and execution scopes."""

    def __init__(
        self,
        project_root: Path,
        shutdown_requested: threading.Event,
    ) -> None:
        self._project_root = project_root
        self._shutdown_requested = shutdown_requested
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

    def record_failure(self, name: str, exc: BaseException) -> str:
        """Update failure health and return the compact exception chain."""

        chain = format_exception_chain(exc)
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
                self.record_failure(name, exc)
                report_observed_failure(
                    exc,
                    component="daemon",
                    event=error_event,
                    message=error_message,
                    project_root=self._project_root,
                    metadata={"worker": name},
                    level="error",
                    status="error",
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
        started_event: str,
        started_message: str,
        error_event: str,
        error_message: str,
    ) -> None:
        """Run an observed operation repeatedly until daemon shutdown."""

        self._worker(name)
        self.write_started(
            name,
            event=started_event,
            message=started_message,
        )
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
        report_observed_failure(
            error,
            component="daemon",
            event="thread_timeout",
            message=f"{name} did not stop within {timeout}s",
            project_root=self._project_root,
            level="warning",
            status="timed_out",
            metadata={
                "worker": name,
                "timeout_seconds": timeout,
                "lifecycle_state": snapshot.state,
            },
        )
        raise error

    def _supervised_target(
        self,
        name: str,
        target: Callable[[], None],
    ) -> Callable[[], None]:
        def run() -> None:
            with runtime_context(source=f"daemon.worker.{name}"):
                try:
                    target()
                except Exception as exc:
                    self.record_failure(name, exc)
                    report_observed_failure(
                        exc,
                        component="daemon",
                        event="worker_exited_unexpectedly",
                        message=f"{name} worker exited unexpectedly",
                        project_root=self._project_root,
                        metadata={"worker": name},
                        level="error",
                        status="error",
                    )

        return run

    def record_success(self, name: str) -> None:
        """Record one successful worker operation."""

        with self._health_lock:
            self._health_for(name)
            self._health[name] = WorkerHealth(
                name=name,
                alive=True,
                last_success_at=utc_now_iso(),
            )

    def write_started(
        self,
        name: str,
        *,
        event: str,
        message: str,
    ) -> None:
        """Write one best-effort worker start audit event."""

        self._worker(name)
        run_observed_best_effort(
            lambda: write_log_event(
                "daemon",
                event,
                message,
                project_root=self._project_root,
                level="info",
                status="started",
                metadata={"worker": name},
            ),
            component="daemon",
            event="worker_start_log_failed",
            message=f"Could not record {name} worker start",
            project_root=self._project_root,
            metadata={"worker": name, "start_event": event},
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
