"""Daemon application state and unified task composition."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from uuid import uuid4

from nuself.agent.chat.composition import ChatResult, compose_conversation_runtime
from nuself.application.projection import publish_chat_observation
from nuself.application.composition import ApplicationGraph
from nuself.reflection.composition import compose_reflection_scheduler
from nuself.reason.composition import compose_reason_advancer
from nuself.agent.text import LangChainTextAgent
from nuself.daemon.activity import ActivityBroker
from nuself.reason.export_service import (
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
    DaemonTaskKind,
    daemon_task,
)
from nuself.log.store import runtime_event_log_sink
from nuself.agent.endpoint import configured_langchain_chat_models
from nuself.delivery.loop import DeliveryLoop
from nuself.delivery.composition import build_delivery_adapters
from nuself.reason.scheduler import ReasonScheduler
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.observability import publish_observed_event
from nuself.runtime.job.message import JobMessage


@dataclass(frozen=True)
class _ChatTaskPayload:
    message: str
    conversation_id: str
    turn_id: str | None


class DaemonUnavailableError(RuntimeError):
    """The daemon cannot safely admit work-plane requests."""


class DaemonState:
    """Own request-facing services and the unified daemon scheduler."""

    def __init__(
        self,
        application: ApplicationGraph,
    ) -> None:
        paths = application.paths
        self.authority_root = paths.authority_root
        self.authority_id = paths.scope.authority_id
        self.shutdown_requested = threading.Event()
        self.activity_broker = ActivityBroker()
        self.event_publisher = EventPublisher()
        self.event_publisher.attach_projection(
            runtime_event_log_sink(
                self.authority_root,
                projection=self.activity_broker.publish,
            )
        )
        config = application.config
        langchain_models = configured_langchain_chat_models(
            self.authority_root,
            config=config,
        )
        self.reason_export_service = ReasonExportService(
            self.authority_root,
            reason_service=application.reason.service,
            task_sink=self._schedule_reason_export,
            language_preference=config.chat.language_preference,
            text_agent=LangChainTextAgent(
                endpoints=langchain_models,
                project_root=self.authority_root,
                component="reasoning",
            ),
        )
        self.conversation_runtime = compose_conversation_runtime(
            paths,
            config,
            application.conversations,
            application.memory_service,
            application.sources,
            application.reflection.service,
            application.reason.service,
            application.trace,
            application.personas,
            job_sink=self.reason_export_service.enqueue,
            section_planner=build_reason_export_section_planner(
                self.authority_root,
                language_preference=config.chat.language_preference,
                langchain_models=langchain_models,
            ),
            event_publisher=self.event_publisher,
            langchain_models=langchain_models,
        )

        self.memory_curator = application.memory_workflows.curator(
            application.trace.recorder,
            config,
            langchain_models=langchain_models,
        )
        self.reflection_scheduler = compose_reflection_scheduler(
            paths,
            application.memory_service,
            application.profiles,
            application.sources,
            application.conversation_history,
            application.reflection.service,
            application.inbox,
            application.deliveries,
            application.trace.recorder,
            config=config.reflection,
            language_preference=config.chat.language_preference,
            langchain_models=langchain_models,
        )
        self.delivery_loop = DeliveryLoop(
            application.inbox,
            application.deliveries,
            build_delivery_adapters(
                paths,
                email_config=config.email,
                macos_config=config.macos_notification,
            ),
        )
        reason_interval = config.daemon.reason_scheduler.interval_seconds
        self.reason_scheduler = ReasonScheduler(
            self.authority_root,
            advancer=compose_reason_advancer(
                paths,
                application.reason.service,
                application.personas,
                application.trace.recorder,
                config,
                readonly_tools=self.conversation_runtime.readonly_tools(),
                langchain_models=langchain_models,
            ),
            interval_seconds=reason_interval,
            service=application.reason.service,
        )
        self._memory_workflows = application.memory_workflows
        memory_interval = config.daemon.memory_curator.interval_seconds
        self._periodic_tasks: tuple[tuple[DaemonTaskKind, float], ...] = (
            ("memory.scan", memory_interval),
            ("conversation.scan", memory_interval),
            (
                "reflection.check",
                config.daemon.reflection_scheduler.check_interval_seconds,
            ),
            ("reason.check", reason_interval),
            (
                "delivery.run",
                config.daemon.delivery.interval_seconds,
            ),
        )
        handlers = {
            "memory.scan": self._scan_memory_observations,
            "memory.curate": self._curate_memory_observation,
            "conversation.scan": self._scan_conversations,
            "chat.turn": self._run_chat_task,
            "conversation.compress": self._compress_conversation,
            "reflection.check": self._check_reflection,
            "reason.check": self._check_reasons,
            "delivery.run": self._run_delivery,
            "reason.export": self._run_reason_export,
        }
        if set(handlers) != set(DAEMON_TASK_KINDS):
            raise RuntimeError("daemon task catalog and handlers differ")
        self.scheduler = DaemonScheduler(
            handlers,
            event_publisher=self.event_publisher,
            project_root=self.authority_root,
        )

    def start_background_tasks(self) -> None:
        """Start one scheduler and admit all recurring responsibilities."""

        self.reason_export_service.recover()
        self.scheduler.start()
        for kind, interval in self._periodic_tasks:
            self.scheduler.submit(
                daemon_task(kind, f"periodic:{kind}", f"schedule:{kind}"),
                delay_seconds=interval,
                interval_seconds=interval,
            )

    def _request_memory_curation(self, observation_id: str) -> None:
        """Admit one coalesced curator task for a durable observation."""

        self._submit_followup(
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
        if not snapshot.running:
            raise DaemonUnavailableError("daemon scheduler is unavailable")
        identity = (
            f"chat.turn:{conversation_id}:{turn_id}"
            if turn_id is not None
            else f"chat.turn:{conversation_id}:{uuid4().hex}"
        )
        completion = self.scheduler.submit(
            daemon_task(
                "chat.turn",
                identity,
                f"conversation:{conversation_id}",
                payload=_ChatTaskPayload(message, conversation_id, turn_id),
                priority=10,
            )
        )
        result = completion.result()
        if not isinstance(result, ChatResult):
            raise TypeError("chat task returned an invalid result")
        return result

    def _scan_memory_observations(self, _task: DaemonTask) -> None:
        for observation in self._memory_workflows.pending_observations():
            self._request_memory_curation(observation.id)

    def _scan_conversations(self, _task: DaemonTask) -> None:
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
            self._memory_workflows,
            turn=result.require_completed_turn(),
            source_trace_id=result.trace_id,
        )
        self._request_memory_curation(observation.id)
        self._request_conversation_compression(result.conversation_id)
        return result

    def _request_conversation_compression(
        self,
        conversation_id: str,
    ) -> None:
        self._submit_followup(
            daemon_task(
                "conversation.compress",
                f"conversation.compress:{conversation_id}",
                f"conversation:{conversation_id}",
                payload=conversation_id,
                priority=120,
            )
        )

    def _submit_followup(self, task: DaemonTask) -> None:
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
                project_root=self.authority_root,
                failure_component="daemon",
            )

    def _compress_conversation(self, task: DaemonTask) -> None:
        conversation_id = task.payload
        if not isinstance(conversation_id, str):
            raise TypeError("compression task requires a conversation ID")
        self.conversation_runtime.compress_conversation(conversation_id)

    def _check_reflection(self, _task: DaemonTask) -> None:
        self.reflection_scheduler.reflect()

    def _check_reasons(self, _task: DaemonTask) -> None:
        self.reason_scheduler.run_once()

    def _run_delivery(self, _task: DaemonTask) -> None:
        self.delivery_loop.run_once()

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
