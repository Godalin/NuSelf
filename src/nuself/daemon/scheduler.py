"""Small typed scheduler shared by every daemon work-plane task."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
import threading
import time
from pathlib import Path
from typing import Literal

from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    use_runtime_context,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.observability import publish_observed_event

type TaskHandler = Callable[["DaemonTask"], object]
type SchedulerPhase = Literal["created", "running", "stopping", "stopped"]


class DaemonSchedulerCapacityError(RuntimeError):
    """Raised when bounded volatile admission is full."""


class DaemonSchedulerStoppedError(RuntimeError):
    """Raised when work is submitted outside the running lifecycle."""


@dataclass(frozen=True)
class DaemonTask:
    """One immutable in-process wake-up for durable domain work."""

    kind: str
    identity: str
    resource: str
    payload: object = None
    priority: int = 100
    context: RuntimeContext = field(default_factory=current_runtime_context)

    def __post_init__(self) -> None:
        for name, value in (
            ("kind", self.kind),
            ("identity", self.identity),
            ("resource", self.resource),
        ):
            if not value.strip():
                raise ValueError(f"daemon task {name} must not be blank")
        if type(self.priority) is not int:
            raise TypeError("daemon task priority must be an integer")


@dataclass(frozen=True)
class DaemonSchedulerSnapshot:
    """Immutable scheduler health view."""

    running: bool
    accepting: bool
    pending: int
    in_flight: int
    capacity: int
    last_error: str | None = None


@dataclass
class _QueuedTask:
    task: DaemonTask
    completion: Future[object]
    run_at: float
    sequence: int
    interval_seconds: float | None = None


class DaemonScheduler:
    """Admit, coalesce, schedule, and resource-serialize daemon tasks."""

    def __init__(
        self,
        handlers: Mapping[str, TaskHandler],
        *,
        max_concurrency: int = 4,
        queue_capacity: int = 256,
        clock: Callable[[], float] = time.monotonic,
        event_publisher: EventPublisher | None = None,
        project_root: Path | None = None,
    ) -> None:
        if not handlers:
            raise ValueError("daemon scheduler requires at least one handler")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be positive")
        if any(not name.strip() for name in handlers):
            raise ValueError("daemon task kinds must not be blank")
        self._handlers = dict(handlers)
        self._max_concurrency = max_concurrency
        self._queue_capacity = queue_capacity
        self._clock = clock
        self._event_publisher = event_publisher
        self._project_root = project_root
        self._condition = threading.Condition()
        self._pending: list[_QueuedTask] = []
        self._active: dict[str, _QueuedTask] = {}
        self._busy_resources: set[str] = set()
        self._sequence = 0
        # Composition and startup recovery may admit work before the
        # dispatcher starts. Shutdown is the only transition that closes it.
        self._phase: SchedulerPhase = "created"
        self._last_error: str | None = None
        self._dispatcher: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="nuself-task",
        )

    def start(self) -> None:
        """Start the sole dispatcher and open admission."""

        with self._condition:
            if self._phase in {"stopping", "stopped"}:
                raise DaemonSchedulerStoppedError(
                    "daemon scheduler has already stopped"
                )
            if self._phase == "running":
                return
            self._phase = "running"
            self._dispatcher = threading.Thread(
                target=self._dispatch,
                name="nuself-scheduler",
                daemon=False,
            )
            self._dispatcher.start()

    def submit(
        self,
        task: DaemonTask,
        *,
        delay_seconds: float = 0.0,
        interval_seconds: float | None = None,
    ) -> Future[object]:
        """Admit one identity or reuse its existing completion."""

        if delay_seconds < 0:
            raise ValueError("task delay must not be negative")
        if interval_seconds is not None and interval_seconds <= 0:
            raise ValueError("task interval must be positive")
        with self._condition:
            if self._phase not in {"created", "running"}:
                raise DaemonSchedulerStoppedError(
                    "daemon scheduler is not accepting tasks"
                )
            if task.kind not in self._handlers:
                raise ValueError(f"unknown daemon task kind: {task.kind}")
            existing = self._active.get(task.identity)
            if existing is not None:
                return existing.completion
            if len(self._active) >= self._queue_capacity:
                raise DaemonSchedulerCapacityError(
                    "daemon scheduler admission is full"
                )
            completion: Future[object] = Future()
            queued = _QueuedTask(
                task=task,
                completion=completion,
                run_at=self._clock() + delay_seconds,
                sequence=self._sequence,
                interval_seconds=interval_seconds,
            )
            self._sequence += 1
            self._pending.append(queued)
            self._active[task.identity] = queued
            self._condition.notify()
            return completion

    def snapshot(self) -> DaemonSchedulerSnapshot:
        with self._condition:
            return DaemonSchedulerSnapshot(
                running=(
                    self._phase == "running"
                    and self._dispatcher is not None
                    and self._dispatcher.is_alive()
                ),
                accepting=self._phase in {"created", "running"},
                pending=len(self._pending),
                in_flight=len(self._busy_resources),
                capacity=self._max_concurrency,
                last_error=self._last_error,
            )

    def shutdown(
        self,
        *,
        timeout: float = 30.0,
        cancel_pending: bool = True,
    ) -> None:
        """Close admission and wait for dispatched work within one budget."""

        if timeout < 0:
            raise ValueError("scheduler shutdown timeout must not be negative")
        deadline = self._clock() + timeout
        with self._condition:
            if self._phase == "stopped":
                return
            self._phase = "stopping"
            if cancel_pending:
                pending = tuple(self._pending)
                self._pending.clear()
                for queued in pending:
                    self._active.pop(queued.task.identity, None)
                    queued.completion.cancel()
            self._condition.notify_all()
        dispatcher = self._dispatcher
        if dispatcher is not None:
            dispatcher.join(max(0.0, deadline - self._clock()))
            if dispatcher.is_alive():
                raise TimeoutError(
                    "daemon scheduler did not stop within its deadline"
                )
        self._executor.shutdown(wait=True, cancel_futures=False)
        with self._condition:
            self._phase = "stopped"

    def _dispatch(self) -> None:
        while True:
            with self._condition:
                queued = self._next_runnable_locked()
                while queued is None:
                    if self._phase == "stopping" and not self._busy_resources:
                        return
                    self._condition.wait(self._wait_timeout_locked())
                    queued = self._next_runnable_locked()
                self._pending.remove(queued)
                self._busy_resources.add(queued.task.resource)
            future = self._executor.submit(self._run, queued.task)
            future.add_done_callback(
                lambda completed, item=queued: self._complete(
                    item, completed
                )
            )

    def _next_runnable_locked(self) -> _QueuedTask | None:
        if len(self._busy_resources) >= self._max_concurrency:
            return None
        now = self._clock()
        eligible = (
            queued
            for queued in self._pending
            if queued.run_at <= now
            and queued.task.resource not in self._busy_resources
        )
        return min(
            eligible,
            key=lambda queued: (
                queued.task.priority,
                queued.run_at,
                queued.sequence,
            ),
            default=None,
        )

    def _wait_timeout_locked(self) -> float | None:
        if len(self._busy_resources) >= self._max_concurrency:
            return None
        runnable_times = [
            queued.run_at
            for queued in self._pending
            if queued.task.resource not in self._busy_resources
        ]
        if not runnable_times:
            return None
        next_run = min(runnable_times)
        return max(0.0, next_run - self._clock())

    def _run(self, task: DaemonTask) -> object:
        context = RuntimeContext(
            conversation_id=task.context.conversation_id,
            reason_id=task.context.reason_id,
            request_id=task.context.request_id,
            turn_id=task.context.turn_id,
            job_id=task.context.job_id,
            trace_id=task.context.trace_id,
            source=f"daemon.task.{task.kind}",
        )
        with use_runtime_context(context):
            self._publish_task_event(task, "task.started", "started")
            try:
                result = self._handlers[task.kind](task)
            except Exception as exc:
                self._publish_task_event(
                    task,
                    "task.failed",
                    "error",
                    error=diagnostic_exception_chain(exc),
                )
                raise
            self._publish_task_event(task, "task.completed", "completed")
            return result

    def _publish_task_event(
        self,
        task: DaemonTask,
        name: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        publisher = self._event_publisher
        if publisher is None:
            return
        publish_observed_event(
            publisher,
            name=name,
            producer="daemon",
            payload=RuntimeLogEventPayload(
                message=f"daemon task {status}",
                level="error" if error is not None else "info",
                status=status,
                error=error,
                metadata={
                    "task_kind": task.kind,
                    "task_identity": task.identity,
                    "resource": task.resource,
                },
            ).to_mapping(),
            project_root=self._project_root,
            failure_component="daemon",
        )

    def _complete(
        self,
        queued: _QueuedTask,
        executed: Future[object],
    ) -> None:
        error = executed.exception()
        result = executed.result() if error is None else None
        with self._condition:
            self._busy_resources.remove(queued.task.resource)
            self._active.pop(queued.task.identity, None)
            if error is not None:
                self._last_error = (
                    f"{queued.task.kind}:{type(error).__name__}"
                )
            else:
                self._last_error = None
            if (
                queued.interval_seconds is not None
                and self._phase == "running"
            ):
                repeated = _QueuedTask(
                    task=queued.task,
                    completion=Future(),
                    run_at=self._clock() + queued.interval_seconds,
                    sequence=self._sequence,
                    interval_seconds=queued.interval_seconds,
                )
                self._sequence += 1
                self._pending.append(repeated)
                self._active[queued.task.identity] = repeated
            self._condition.notify_all()
        if error is None:
            queued.completion.set_result(result)
        else:
            queued.completion.set_exception(error)
