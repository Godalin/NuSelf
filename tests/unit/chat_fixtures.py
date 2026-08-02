"""Explicit ConversationGraphRuntime composition for tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.chat.runtime import (
    ConversationGraphRuntime as _ConversationGraphRuntime,
)
from nuself.agent.chat.types import ChatAgentSettings
from conversation_fixtures import ConversationStore
from nuself.agent.chat.response import ConversationResponseService
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.tools.resources import ToolResources
from nuself.agent.text import LangChainTextAgent, TextAgent
from nuself.application.composition import compose_application
from nuself.application.knowledge_projection import load_personas_from_memory
from nuself.config import runtime_paths
from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.logs import runtime_event_log_sink
from nuself.memory.query import MemoryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
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
from nuself.runtime.events import EventPublisher
from nuself.runtime.jobs import JobSink
from nuself.runtime.frontend import ApprovalPort
from tests.backend import owned_backend
from nuself.trace.service import TraceQueryService, TraceRecorder
from nuself.workspace import PrivateWorkspaceStore


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
        source_repository: SourceRepository | None = None,
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
        sources = source_repository or application.memory.sources
        profile = profile_repository or application.memory.profile
        reflections = (
            application.reflection_service
            if reflection_repository is None
            else ReflectionService(
                reflection_repository,
                application.reason_service,
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
                or MemoryService(entries, sources, profile),
                reflections=reflections,
                reasons=reason_service
                or application.reason_service,
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
                        repository=application.persona_prompts,
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
            conversation_store=conversation_store or application.conversations,
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
