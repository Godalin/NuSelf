"""Shared conversation-runtime composition for direct and daemon surfaces."""

from __future__ import annotations

from nuself.agent.chat import ConversationGraphRuntime, ThreadStore
from nuself.application.composition import ApplicationGraph
from nuself.memory.query import MemoryQueryService
from nuself.persona.tools import build_persona_tools
from nuself.reason.output import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.runtime.events import EventPublisher
from nuself.runtime.jobs import JobSink


def compose_conversation_runtime(
    application: ApplicationGraph,
    *,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
    event_publisher: EventPublisher | None = None,
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
        source_repository=application.memory.sources,
        profile_repository=application.memory.profile,
        reflection_repository=application.reflection,
        trace_recorder=application.trace.recorder,
        reason_service=ReasonService(
            paths.project_root,
            repository=application.reason,
            trace_recorder=application.trace.recorder,
        ),
        trace_query_service=application.trace.query,
        persona_tools=build_persona_tools(
            paths.project_root,
            repository=application.persona_prompts,
            trace_recorder=application.trace.recorder,
        ),
        thread_store=ThreadStore(
            paths.project_root,
            backend=application.backend,
        ),
        job_sink=job_sink,
        section_planner=section_planner,
        event_publisher=event_publisher,
    )
