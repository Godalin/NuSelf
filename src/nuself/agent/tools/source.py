"""Source-owned read-only agent tools."""

from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.source.repository import SourceChunkNotFound, SourceDocumentNotFound
from nuself.source.service import SourceMatch, SourceService


def build_source_tools(service: SourceService, *, project_root: Path, executor: FeatureExecutor) -> tuple[BaseTool, ...]:
    @tool(name="source_search", description="Search imported external documents when the current question needs reference material.")
    @component("source")
    @readonly
    @observed
    def search(query: str, limit: int = 8) -> str:
        if not query.strip() or limit < 1:
            return "Error: query must be non-empty and limit must be positive"
        matches = service.search(query, limit=limit)
        if not matches:
            return "No source matches. Retry once with a broader query when useful."
        return "\n".join(_format_match(match) for match in matches)

    @tool(name="source_get", description="Read one imported source document or chunk by its stable id.")
    @component("source")
    @readonly
    @observed
    def get(source_id: str) -> str:
        try:
            if "_chunk_" in source_id:
                chunk = service.get_chunk(source_id)
                return f"{chunk.source_ref} {chunk.title}\n{chunk.text}"
            document = service.get(source_id)
        except (SourceDocumentNotFound, SourceChunkNotFound):
            return f"Source record not found: {source_id}"
        return f"{document.id} {document.title}\npath={document.path} tags={','.join(document.tags)}"

    @tool(name="source_list", description="List imported external source documents and their stable ids.")
    @component("source")
    @readonly
    @observed
    def list_sources(limit: int = 20) -> str:
        documents = service.list()[:max(limit, 1)]
        return "\n".join(f"- {item.id} {item.title} path={item.path}" for item in documents) or "No source documents."

    return (
        materialize_tool(search, executor=executor),
        materialize_tool(get, executor=executor),
        materialize_tool(list_sources, executor=executor),
    )


def _format_match(match: SourceMatch) -> str:
    return (
        f"- {match.document.title} [ref={match.chunk.source_ref} id={match.chunk.id} "
        f"match={','.join(match.reasons)}]: {match.chunk.text}"
    )
