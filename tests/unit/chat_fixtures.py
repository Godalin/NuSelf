"""Explicit ConversationGraphRuntime composition for tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.chat import (
    ChatAgentSettings,
    ConversationGraphRuntime as _ConversationGraphRuntime,
)
from conversation_fixtures import ConversationStore
from nuself.agent.chat.response import ConversationResponseService
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.tools.resources import ToolResources
from nuself.agent.text import TextAgent
from nuself.application.composition import compose_application
from nuself.application.persona import load_personas_from_memory
from nuself.application.reason import compose_reason_service
from nuself.config import runtime_paths
from nuself.llm import LangChainLLMEndpoint
from nuself.memory.query import MemoryQueryService
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
from nuself.runtime.events import EventPublisher
from nuself.runtime.jobs import JobSink
from nuself.runtime.frontend import ApprovalPort
from nuself.storage import get_default_backend
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
        memory_query_service: MemoryQueryService | None = None,
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
            get_default_backend(project_root),
        )
        entries = memory_repository or application.memory.entries
        sources = source_repository or application.memory.sources
        profile = profile_repository or application.memory.profile
        resources = ConversationResources(
            tools=ToolResources(
                project_root=project_root,
                memory_query=memory_query_service
                or MemoryQueryService(entries, sources, profile),
                memory=entries,
                reflections=reflection_repository
                or application.reflection,
                reasons=reason_service
                or compose_reason_service(application),
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
        )
        super().__init__(
            resources,
            langchain_models=langchain_models,
            settings=settings,
            event_publisher=event_publisher,
            response_service=response_service,
            compression_agent=compression_agent,
            approval_port=approval_port,
        )
