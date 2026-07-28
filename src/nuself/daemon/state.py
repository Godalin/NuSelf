"""Daemon subsystem and worker-target composition."""

from __future__ import annotations

import threading
from pathlib import Path

from nuself.agent.chat import ChatAgent
from nuself.config import ConfigSystem
from nuself.daemon.activity import ActivityBroker
from nuself.daemon.reason_export import (
    ReasonExportWorker,
    build_reason_export_section_planner,
)
from nuself.daemon.types import WorkerHealth
from nuself.daemon.workers import DaemonWorkerSupervisor
from nuself.logs import runtime_event_log_sink
from nuself.memory.curator import MemoryCurator
from nuself.notification import (
    NotificationAdapter,
    NotificationDeliveryLoop,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter
from nuself.reason import ReasonScheduler
from nuself.reflection import ReflectionScheduler
from nuself.runtime.events import EventPublisher


class DaemonState:
    """Own request-facing services and concrete daemon worker targets."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.activity_broker = ActivityBroker()
        self.event_publisher = EventPublisher()
        self.event_publisher.subscribe(
            runtime_event_log_sink(project_root)
        )
        self._worker_supervisor = DaemonWorkerSupervisor(
            project_root,
            self.shutdown_requested,
            self.event_publisher,
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
            event_publisher=self.event_publisher,
        )

        config = ConfigSystem.load(project_root=project_root)
        self.memory_curator = MemoryCurator(project_root)
        self.memory_curator_interval_seconds: float = (
            config.daemon.memory_curator.interval_seconds
        )
        self.reflection_scheduler = ReflectionScheduler(project_root)
        self.reflection_check_interval_seconds: float = (
            config.daemon.reflection_scheduler.check_interval_seconds
        )

        adapters: list[NotificationAdapter] = []
        if config.email.enabled:
            adapters.append(EmailNotificationAdapter(project_root))
        if config.macos_notification.enabled:
            adapters.append(MacOSNotificationAdapter(project_root))
        self.notification_delivery_loop = NotificationDeliveryLoop(
            project_root,
            adapters=adapters if adapters else None,
        )
        self.notification_delivery_interval_seconds: float = (
            config.daemon.notification_delivery.interval_seconds
        )

        self.reason_scheduler: ReasonScheduler | None = None
        self.reason_scheduler_interval_seconds = (
            config.daemon.reason_scheduler.interval_seconds
        )
        self._reason_scheduler_start_lock = threading.Lock()
        self._export_worker_start_lock = threading.Lock()
        self._register_workers()

    def worker_health(self) -> tuple[WorkerHealth, ...]:
        """Return a stable snapshot of daemon worker health."""

        return self._worker_supervisor.health()

    def start_background_memory_curator(self) -> None:
        self._worker_supervisor.start("memory_curator")

    def stop_background_memory_curator(self) -> None:
        self._worker_supervisor.join("memory_curator")

    def start_background_reflection_scheduler(self) -> None:
        self._worker_supervisor.start("reflection_scheduler")

    def stop_background_reflection_scheduler(self) -> None:
        self._worker_supervisor.join("reflection_scheduler")

    def start_background_reason_scheduler(self) -> None:
        with self._reason_scheduler_start_lock:
            if (
                self._worker_supervisor.snapshot(
                    "reason_scheduler"
                ).state
                != "new"
            ):
                return
            tools = getattr(self.chat_agent, "_tools", None)
            readonly_tools = (
                [
                    tool
                    for tool in tools.values()
                    if "readonly" in (tool.tags or [])
                ]
                if tools
                else None
            )
            langchain_models = getattr(
                self.chat_agent,
                "_langchain_models",
                None,
            )
            self.reason_scheduler = ReasonScheduler(
                self.project_root,
                interval_seconds=self.reason_scheduler_interval_seconds,
                readonly_tools=readonly_tools,
                langchain_models=langchain_models,
            )
            self._worker_supervisor.start("reason_scheduler")

    def stop_background_reason_scheduler(self) -> None:
        self._worker_supervisor.join("reason_scheduler")

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

    def start_background_notification_delivery(self) -> None:
        self._worker_supervisor.start("notification_delivery")

    def stop_background_notification_delivery(self) -> None:
        self._worker_supervisor.join("notification_delivery")

    def _register_workers(self) -> None:
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

    def _run_background_memory_curator(self) -> None:
        self._worker_supervisor.run_scheduled(
            "memory_curator",
            self.memory_curator.run_once,
            interval_seconds=self.memory_curator_interval_seconds,
            error_event="memory_curator_error",
            error_message="memory curator iteration failed",
        )

    def _run_background_reflection_scheduler(self) -> None:
        def run_once() -> None:
            if self.reflection_scheduler.should_reflect():
                self.reflection_scheduler.reflect()

        self._worker_supervisor.run_scheduled(
            "reflection_scheduler",
            run_once,
            interval_seconds=self.reflection_check_interval_seconds,
            error_event="reflection_scheduler_error",
            error_message="reflection scheduler iteration failed",
        )

    def _run_background_reason_scheduler(self) -> None:
        def run_once() -> None:
            if self.reason_scheduler is None:
                raise RuntimeError("reason scheduler was not initialized")
            self.reason_scheduler.run_once()

        self._worker_supervisor.run_scheduled(
            "reason_scheduler",
            run_once,
            interval_seconds=self.reason_scheduler_interval_seconds,
            error_event="reason_scheduler_error",
            error_message="reason scheduler iteration failed",
        )

    def _run_background_notification_delivery(self) -> None:
        self._worker_supervisor.run_scheduled(
            "notification_delivery",
            self.notification_delivery_loop.run_once,
            interval_seconds=self.notification_delivery_interval_seconds,
            error_event="notification_delivery_error",
            error_message="notification delivery iteration failed",
        )
