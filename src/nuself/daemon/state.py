"""Daemon application state and unified task composition."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from nuself.application.chat import ChatResult, compose_conversation_runtime
from nuself.application.curator import compose_memory_curator
from nuself.application.knowledge_projection import publish_chat_observation
from nuself.application.runtime import (
    ApplicationRuntime,
    current_application_runtime,
    open_application_runtime,
)
from nuself.application.reflection import compose_reflection_scheduler
from nuself.application.reason import (
    compose_reason_advancer,
    compose_reason_service,
)
from nuself.config import ConfigSystem
from nuself.conversation import CompletedTurn
from nuself.daemon.activity import ActivityBroker
from nuself.daemon.reason_export import (
    ReasonExportService,
    build_reason_export_section_planner,
)
from nuself.daemon.scheduler import (
    DaemonScheduler,
    DaemonSchedulerCapacityError,
    DaemonSchedulerStoppedError,
    DaemonTask,
)
from nuself.daemon.tasks import (
    DAEMON_TASK_KINDS,
    PeriodicTaskKind,
    daemon_task,
)
from nuself.logs import runtime_event_log_sink
from nuself.notification import (
    NotificationDeliveryLoop,
)
from nuself.notification.composition import build_notification_adapters
from nuself.reason import ReasonScheduler
from nuself.runtime.events import EventPublisher
from nuself.runtime.event_payloads import RuntimeLogEventPayload
from nuself.runtime.observability import publish_observed_event
from nuself.runtime.jobs import JobMessage
from nuself.workspace import PrivateWorkspaceStore


@dataclass(frozen=True)
class _ChatTaskPayload:
    message: str
    conversation_id: str
    turn_id: str | None


def _require_completed_turn(result: ChatResult) -> CompletedTurn:
    turn = result.completed_turn
    if turn is None:
        raise RuntimeError("conversation result is missing its committed turn")
    return turn


class DaemonUnavailableError(RuntimeError):
    """The daemon cannot safely admit work-plane requests."""


class DaemonState:
    """Own request-facing services and the unified daemon scheduler."""

    def __init__(
        self,
        project_root: Path,
        *,
        application_runtime: ApplicationRuntime | None = None,
    ) -> None:
        self.project_root = project_root
        self.application_runtime = (
            application_runtime
            or current_application_runtime()
            or open_application_runtime(project_root)
        )
        paths = self.application_runtime.paths
        self.authority_id = paths.scope.authority_id
        self.application = self.application_runtime.application
        self.shutdown_requested = threading.Event()
        self.activity_broker = ActivityBroker()
        self.event_publisher = EventPublisher()
        self.event_publisher.attach_projection(
            runtime_event_log_sink(
                project_root,
                projection=self.activity_broker.publish,
            )
        )
        self.reason_export_service = ReasonExportService(
            project_root,
            reason_service=compose_reason_service(self.application),
            workspace_store=PrivateWorkspaceStore(
                paths,
                scope="reason",
            ),
        )
        self.conversation_runtime = compose_conversation_runtime(
            self.application,
            job_sink=self.reason_export_service.enqueue,
            section_planner=build_reason_export_section_planner(
                project_root
            ),
            event_publisher=self.event_publisher,
        )

        config = ConfigSystem.load(project_root=project_root)
        self.memory_curator = compose_memory_curator(self.application)
        self.memory_curator_interval_seconds: float = (
            config.daemon.memory_curator.interval_seconds
        )
        self.reflection_scheduler = compose_reflection_scheduler(
            self.application,
            config=config.reflection,
            language_preference=config.chat.language_preference,
        )
        self.reflection_check_interval_seconds: float = (
            config.daemon.reflection_scheduler.check_interval_seconds
        )

        self.notification_delivery_loop = NotificationDeliveryLoop(
            self.application.notifications,
            build_notification_adapters(
                paths,
                config=config,
            ),
        )
        self.notification_delivery_interval_seconds: float = (
            config.daemon.notification_delivery.interval_seconds
        )

        self.reason_scheduler_interval_seconds = (
            config.daemon.reason_scheduler.interval_seconds
        )
        capabilities = self.conversation_runtime.capability_snapshot()
        self.reason_scheduler = ReasonScheduler(
            self.project_root,
            advancer=compose_reason_advancer(
                self.application,
                readonly_tools=capabilities.readonly_tools,
                langchain_models=capabilities.endpoints,
            ),
            interval_seconds=self.reason_scheduler_interval_seconds,
            repository=self.application.reason,
            service=compose_reason_service(self.application),
        )
        handlers = {
            "memory.scan": self._scan_memory_observations,
            "memory.curate": self._curate_memory_observation,
            "conversation.scan": self._scan_conversations,
            "chat.turn": self._run_chat_task,
            "conversation.compress": self._compress_conversation,
            "reflection.check": self._check_reflection,
            "reason.check": self._check_reasons,
            "notification.deliver": self._deliver_notifications,
            "reason.export": self._run_reason_export,
        }
        if set(handlers) != set(DAEMON_TASK_KINDS):
            raise RuntimeError("daemon task catalog and handlers differ")
        self.scheduler = DaemonScheduler(
            handlers,
            event_publisher=self.event_publisher,
            project_root=project_root,
        )
        self.reason_export_service.bind_task_sink(
            self._schedule_reason_export
        )

    def scheduler_health(self):
        """Return the unified scheduler snapshot."""

        return self.scheduler.snapshot()

    def require_scheduler_ready(self) -> None:
        """Require the dispatcher to remain alive before readiness."""

        if not self.scheduler.snapshot().running:
            raise RuntimeError("daemon scheduler is not running")

    def start_background_tasks(self) -> None:
        """Start one scheduler and admit all recurring responsibilities."""

        self.reason_export_service.prepare()
        self.reason_export_service.recover()
        self.scheduler.start()
        self._schedule_periodic(
            "memory.scan",
            self.memory_curator_interval_seconds,
        )
        self._schedule_periodic(
            "conversation.scan",
            self.memory_curator_interval_seconds,
        )
        self._schedule_periodic(
            "reflection.check",
            self.reflection_check_interval_seconds,
        )
        self._schedule_periodic(
            "reason.check",
            self.reason_scheduler_interval_seconds,
        )
        self._schedule_periodic(
            "notification.deliver",
            self.notification_delivery_interval_seconds,
        )

    def stop_background_tasks(self) -> None:
        self.scheduler.shutdown()

    def request_memory_curation(self, observation_id: str) -> bool:
        """Admit one coalesced curator task for a durable observation."""

        return self._submit_followup(
            daemon_task(
                "memory.curate",
                f"memory.curate:{observation_id}",
                f"memory-observation:{observation_id}",
                payload=observation_id,
            )
        )

    def run_chat(
        self,
        message: str,
        *,
        conversation_id: str,
        turn_id: str | None,
    ) -> ChatResult:
        """Run chat through its conversation resource lane in a live daemon."""

        snapshot = self.scheduler.snapshot()
        if not snapshot.running or not snapshot.accepting:
            raise DaemonUnavailableError("daemon scheduler is unavailable")
        identity = (
            f"chat.turn:{conversation_id}:{turn_id}"
            if turn_id is not None
            else f"chat.turn:{conversation_id}:{uuid4().hex}"
        )
        submission = self.scheduler.submit(
            daemon_task(
                "chat.turn",
                identity,
                f"conversation:{conversation_id}",
                payload=_ChatTaskPayload(message, conversation_id, turn_id),
                priority=10,
            )
        )
        result = submission.completion.result()
        if not isinstance(result, ChatResult):
            raise TypeError("chat task returned an invalid result")
        return result

    def _schedule_periodic(
        self,
        kind: PeriodicTaskKind,
        interval: float,
    ) -> None:
        self.scheduler.submit(
            daemon_task(kind, f"periodic:{kind}", f"schedule:{kind}"),
            delay_seconds=interval,
            interval_seconds=interval,
        )

    def _scan_memory_observations(self, task: DaemonTask) -> None:
        del task
        for observation in self.application.memory.observations.pending():
            self.request_memory_curation(observation.id)

    def _scan_conversations(self, task: DaemonTask) -> None:
        del task
        for conversation_id in (
            self.conversation_runtime.conversations_requiring_compression()
        ):
            self._request_conversation_compression(conversation_id)

    def _curate_memory_observation(self, task: DaemonTask) -> None:
        observation_id = task.payload
        if not isinstance(observation_id, str):
            raise TypeError("memory curator task requires an observation ID")
        self.memory_curator.run_once(observation_id)

    def _run_chat_task(self, task: DaemonTask) -> ChatResult:
        payload = task.payload
        if not isinstance(payload, _ChatTaskPayload):
            raise TypeError("chat task requires a typed payload")
        result = self.conversation_runtime.respond(
            payload.message,
            conversation_id=payload.conversation_id,
            turn_id=payload.turn_id,
        )
        observation = publish_chat_observation(
            self.application.memory.observations,
            turn=_require_completed_turn(result),
            source_trace_id=result.trace_id,
        )
        self.request_memory_curation(observation.id)
        self._request_conversation_compression(result.conversation_id)
        return result

    def _request_conversation_compression(
        self,
        conversation_id: str,
    ) -> bool:
        return self._submit_followup(
            daemon_task(
                "conversation.compress",
                f"conversation.compress:{conversation_id}",
                f"conversation:{conversation_id}",
                payload=conversation_id,
                priority=120,
            )
        )

    def _submit_followup(self, task: DaemonTask) -> bool:
        try:
            self.scheduler.submit(task)
        except (
            DaemonSchedulerCapacityError,
            DaemonSchedulerStoppedError,
        ) as exc:
            publish_observed_event(
                self.event_publisher,
                name="task.deferred",
                producer="daemon",
                payload=RuntimeLogEventPayload(
                    message="durable daemon follow-up deferred",
                    level="warning",
                    status="deferred",
                    metadata={
                        "task_kind": task.kind,
                        "resource": task.resource,
                        "error_type": type(exc).__name__,
                    },
                ).to_mapping(),
                project_root=self.project_root,
                failure_component="daemon",
            )
            return False
        return True

    def _compress_conversation(self, task: DaemonTask) -> None:
        conversation_id = task.payload
        if not isinstance(conversation_id, str):
            raise TypeError("compression task requires a conversation ID")
        self.conversation_runtime.compress_conversation(conversation_id)

    def _check_reflection(self, task: DaemonTask) -> None:
        del task
        if self.reflection_scheduler.should_reflect():
            self.reflection_scheduler.reflect()

    def _check_reasons(self, task: DaemonTask) -> None:
        del task
        self.reason_scheduler.run_once()

    def _deliver_notifications(self, task: DaemonTask) -> None:
        del task
        self.notification_delivery_loop.run_once()

    def _schedule_reason_export(
        self,
        message: JobMessage,
        delay_seconds: float,
    ) -> None:
        attempt = message.payload.get("attempt", 0)
        self.scheduler.submit(
            daemon_task(
                "reason.export",
                f"reason.export:{message.job_id}:{message.resource_id}:{attempt}",
                f"reason:{message.resource_id}",
                payload=message,
                priority=50,
                context=replace(
                    message.envelope.context,
                    reason_id=message.resource_id,
                    job_id=message.job_id,
                ),
            ),
            delay_seconds=delay_seconds,
        )

    def _run_reason_export(self, task: DaemonTask) -> None:
        message = task.payload
        if not isinstance(message, JobMessage):
            raise TypeError("reason export task requires a JobMessage")
        self.reason_export_service.process(message)
