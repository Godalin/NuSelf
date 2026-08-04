"""Explicit ConversationGraphRuntime composition for tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.chat.engine import (
    ConversationGraphRuntime as _ConversationGraphRuntime,
)
from nuself.agent.chat.types import ChatAgentSettings
from conversation_fixtures import ConversationStore
from nuself.conversation import ConversationService
from nuself.agent.chat.response import ConversationResponseService
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.tools.resources import ToolResources
from nuself.agent.text import LangChainTextAgent, TextAgent
from nuself.application.composition import compose_application
from nuself.application.projection import load_personas_from_memory
from nuself.config.settings import runtime_paths
from nuself.agent.endpoint import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.log.store import runtime_event_log_sink
from nuself.memory.service import MemoryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.source.service import SourceService
from nuself.persona.tools import build_persona_tools
from nuself.persona.definition import (
    PersonaDefinition,
)
from nuself.profile.repository import ProfileItemRepository
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.service import ReflectionService
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.job.message import JobSink
from nuself.runtime.frontend import ApprovalPort
from tests.backend import owned_backend
from nuself.trace.service import TraceQueryService, TraceRecorder
from nuself.storage.workspace import PrivateWorkspaceStore


class ConversationGraphRuntime(_ConversationGraphRuntime):
    """Test wrapper that supplies a complete authority graph."""

    def __init__(
        self,
        project_root: Path,
        *,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
        settings: ChatAgentSettings | None = None,
        memory_query_service: MemoryService | None = None,
        conversation_store: ConversationStore | None = None,
        job_sink: JobSink | None = None,
        section_planner: SectionPlanner | None = None,
        event_publisher: EventPublisher | None = None,
        response_service: ConversationResponseService | None = None,
        compression_agent: TextAgent | None = None,
        memory_repository: MemoryEntryRepository | None = None,
        source_service: SourceService | None = None,
        profile_repository: ProfileItemRepository | None = None,
        reflection_repository: ReflectionRepository | None = None,
        trace_recorder: TraceRecorder | None = None,
        reason_service: ReasonService | None = None,
        trace_query_service: TraceQueryService | None = None,
        persona_tools: Sequence[BaseTool] | None = None,
        persona_definitions: tuple[PersonaDefinition, ...] | None = None,
        approval_port: ApprovalPort | None = None,
    ) -> None:
        application = compose_application(
            runtime_paths(project_root),
            owned_backend(project_root),
        )
        effective_models = (
            langchain_models
            if langchain_models is not None
            else configured_langchain_chat_models(
                project_root,
                config=application.config,
            )
        )
        entries = memory_repository or application.memory.entries
        sources = source_service or application.sources
        del profile_repository
        reflections = (
            application.reflection.service
            if reflection_repository is None
            else ReflectionService(
                reflection_repository,
                application.reason.service,
                application.trace.recorder,
                ReflectionOrganizer(
                    project_root,
                    repository=reflection_repository,
                ),
            )
        )
        resources = ConversationResources(
            tools=ToolResources(
                project_root=project_root,
                memory=memory_query_service
                or MemoryService(entries),
                sources=sources,
                reflections=reflections,
                reasons=reason_service
                or application.reason.service,
                reason_workspace=PrivateWorkspaceStore(
                    runtime_paths(project_root),
                    scope="reason",
                ),
                traces=trace_query_service
                or application.trace.query,
                persona_tools=tuple(
                    persona_tools
                    or build_persona_tools(
                        project_root,
                        repository=application.personas,
                        trace_recorder=application.trace.recorder,
                        text_agent=LangChainTextAgent(
                            endpoints=effective_models,
                            project_root=project_root,
                            component="persona",
                        ),
                    )
                ),
                job_sink=job_sink,
                section_planner=section_planner,
            ),
            trace_recorder=trace_recorder
            or application.trace.recorder,
            personas=persona_definitions
            or load_personas_from_memory(
                application.memory.entries,
                project_root=project_root,
            ),
            conversation_store=(
                ConversationService(conversation_store)
                if conversation_store is not None
                else application.conversations
            ),
            reflection_settings=application.config.reflection,
            language_preference=application.config.chat.language_preference,
        )
        publisher = event_publisher
        if publisher is None:
            publisher = EventPublisher()
            publisher.attach_projection(runtime_event_log_sink(project_root))
        super().__init__(
            resources,
            langchain_models=effective_models,
            settings=settings or ChatAgentSettings(
                recent_messages=(
                    application.config.chat.context.recent_messages
                ),
                summary_trigger_messages=(
                    application.config.chat.context.summary_trigger_messages
                ),
                summary_target_chars=(
                    application.config.chat.context.summary_target_chars
                ),
            ),
            event_publisher=publisher,
            response_service=response_service,
            compression_agent=compression_agent,
            approval_port=approval_port,
        )
