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
from nuself.daemon.activity import ActivityBroker
from nuself.daemon.reason_export import (
    ReasonExportService,
    build_reason_export_section_planner,
)
from nuself.daemon.scheduler import DaemonScheduler, DaemonTask
from nuself.logs import runtime_event_log_sink
from nuself.notification import (
    NotificationDeliveryLoop,
)
from nuself.notification.composition import build_notification_adapters
from nuself.reason import ReasonScheduler
from nuself.runtime.events import EventPublisher
from nuself.runtime.jobs import JobMessage
from nuself.workspace import PrivateWorkspaceStore


@dataclass(frozen=True)
class _ChatTaskPayload:
    message: str
    conversation_id: str
    turn_id: str | None


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
            runtime_event_log_sink(project_root)
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
            paths,
            self.application.backend,
            config=config.reflection,
            repository=self.application.reflection,
            outbox=self.application.notifications,
            trace_recorder=self.application.trace.recorder,
            memory_repository=self.application.memory.entries,
            source_repository=self.application.memory.sources,
            profile_repository=self.application.memory.profile,
            conversation_history=self.application.conversation_history,
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
        self.scheduler = DaemonScheduler(
            {
                "memory.scan": self._scan_memory_observations,
                "memory.curate": self._curate_memory_observation,
                "chat.turn": self._run_chat_task,
                "conversation.compress": self._compress_conversation,
                "reflection.check": self._check_reflection,
                "reason.check": self._check_reasons,
                "notification.deliver": self._deliver_notifications,
                "reason.export": self._run_reason_export,
            },
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

    def request_memory_curation(self, observation_id: str) -> None:
        """Admit one coalesced curator task for a durable observation."""

        self.scheduler.submit(
            DaemonTask(
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

        if not self.scheduler.snapshot().running:
            result = self.conversation_runtime.respond(
                message,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
            observation = publish_chat_observation(
                self.application,
                result=result,
                user_message=message,
                turn_id=turn_id,
            )
            self.request_memory_curation(observation.id)
            return result
        identity = (
            f"chat.turn:{conversation_id}:{turn_id}"
            if turn_id is not None
            else f"chat.turn:{conversation_id}:{uuid4().hex}"
        )
        submission = self.scheduler.submit(
            DaemonTask(
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

    def _schedule_periodic(self, kind: str, interval: float) -> None:
        self.scheduler.submit(
            DaemonTask(kind, f"periodic:{kind}", f"schedule:{kind}"),
            delay_seconds=interval,
            interval_seconds=interval,
        )

    def _scan_memory_observations(self, task: DaemonTask) -> None:
        del task
        for observation in self.application.memory.observations.pending():
            self.request_memory_curation(observation.id)

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
            self.application,
            result=result,
            user_message=payload.message,
            turn_id=payload.turn_id,
        )
        self.request_memory_curation(observation.id)
        self.scheduler.submit(
            DaemonTask(
                "conversation.compress",
                f"conversation.compress:{result.conversation_id}",
                f"conversation:{result.conversation_id}",
                payload=result.conversation_id,
                priority=120,
            )
        )
        return result

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
            DaemonTask(
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
