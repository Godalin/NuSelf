"""Shared conversation-runtime composition for direct and daemon surfaces."""

from __future__ import annotations

from nuself.agent.chat import (
    ChatAgentSettings,
    ChatResult,
    ConversationGraphRuntime,
)
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.tools.resources import ToolResources
from nuself.agent.chat.response import ConversationResponseService
from nuself.application.composition import ApplicationGraph
from nuself.persona.tools import build_persona_tools
from nuself.application.persona import load_personas_from_memory
from nuself.reason.output_contracts import SectionPlanner
from nuself.runtime.events import EventPublisher
from nuself.runtime.frontend import ApprovalPort
from nuself.runtime.jobs import JobSink
from nuself.workspace import PrivateWorkspaceStore
from nuself.config import ConfigSystem
from nuself.llm import configured_langchain_chat_models

__all__ = ["ChatResult", "compose_conversation_runtime"]


def compose_conversation_runtime(
    application: ApplicationGraph,
    *,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
    event_publisher: EventPublisher | None = None,
    response_service: ConversationResponseService | None = None,
    approval_port: ApprovalPort | None = None,
) -> ConversationGraphRuntime:
    """Build chat from one authority graph plus surface-owned adapters."""

    paths = application.paths
    config = ConfigSystem.load(project_root=paths.project_root)
    resources = ConversationResources(
        tools=ToolResources(
            project_root=paths.project_root,
            memory_query=application.memory_query,
            memory=application.memory.entries,
            reflections=application.reflection,
            reasons=application.reason_service,
            reason_workspace=PrivateWorkspaceStore(
                paths,
                scope="reason",
            ),
            traces=application.trace.query,
            persona_tools=tuple(
                build_persona_tools(
                    paths.project_root,
                    repository=application.persona_prompts,
                    trace_recorder=application.trace.recorder,
                )
            ),
            job_sink=job_sink,
            section_planner=section_planner,
        ),
        trace_recorder=application.trace.recorder,
        personas=load_personas_from_memory(
            application.memory.entries,
            project_root=paths.project_root,
        ),
        conversation_store=application.conversations,
        language_preference=config.chat.language_preference,
    )
    return ConversationGraphRuntime(
        resources,
        langchain_models=configured_langchain_chat_models(paths.project_root),
        settings=ChatAgentSettings(
            recent_messages=config.chat.context.recent_messages,
            summary_trigger_messages=(
                config.chat.context.summary_trigger_messages
            ),
            summary_target_chars=config.chat.context.summary_target_chars,
        ),
        event_publisher=event_publisher,
        response_service=response_service,
        approval_port=approval_port,
    )
