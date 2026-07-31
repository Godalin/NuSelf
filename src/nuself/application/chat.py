"""Shared conversation-runtime composition for direct and daemon surfaces."""

from __future__ import annotations

from nuself.agent.chat import ConversationGraphRuntime
from nuself.agent.chat.response import ConversationResponseService
from nuself.application.composition import ApplicationGraph
from nuself.memory.query import MemoryQueryService
from nuself.persona.tools import build_persona_tools
from nuself.persona.definition import load_persona_definitions
from nuself.reason.output_contracts import SectionPlanner
from nuself.application.reason import compose_reason_service
from nuself.application.thread import compose_thread_store
from nuself.runtime.events import EventPublisher
from nuself.runtime.jobs import JobSink
from nuself.workspace import PrivateWorkspaceStore


def compose_conversation_runtime(
    application: ApplicationGraph,
    *,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
    event_publisher: EventPublisher | None = None,
    response_service: ConversationResponseService | None = None,
) -> ConversationGraphRuntime:
    """Build chat from one authority graph plus surface-owned adapters."""

    paths = application.paths
    return ConversationGraphRuntime(
        paths.project_root,
        memory_query_service=MemoryQueryService(
            application.memory.entries,
            application.memory.sources,
            application.memory.profile,
        ),
        memory_repository=application.memory.entries,
        reflection_repository=application.reflection,
        trace_recorder=application.trace.recorder,
        reason_service=compose_reason_service(application),
        reason_workspace_store=PrivateWorkspaceStore(
            paths,
            scope="reason",
        ),
        trace_query_service=application.trace.query,
        persona_tools=build_persona_tools(
            paths.project_root,
            repository=application.persona_prompts,
            trace_recorder=application.trace.recorder,
        ),
        persona_definitions=load_persona_definitions(
            application.memory.entries,
            project_root=paths.project_root,
        ),
        thread_store=compose_thread_store(application),
        job_sink=job_sink,
        section_planner=section_planner,
        event_publisher=event_publisher,
        response_service=response_service,
    )
