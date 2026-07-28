"""Workspace-owned framework tool definitions."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import cast

from langchain_core.tools import BaseTool

from nuself.agent.tools.common import structured_tool_factory
from nuself.store import ScopedWorkspace


def build_workspace_tools(
    workspace: ScopedWorkspace,
) -> tuple[BaseTool, ...]:
    """Build tools for a concrete thread-scoped workspace."""
    return build_workspace_tools_from_provider(lambda: workspace)


def build_workspace_tools_from_provider(
    workspace_provider: Callable[[], ScopedWorkspace],
) -> tuple[BaseTool, ...]:
    """Build workspace tools that resolve the active workspace lazily."""
    tool_from_function = structured_tool_factory()

    def put(
        key: str,
        value: str,
        sub_namespace: str | None = None,
    ) -> str:
        """Store a JSON value under the given key in the thread's workspace."""
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return "Error: value must be a valid JSON string"
        if not isinstance(parsed, dict):
            return "Error: value must be a JSON object (dict)"
        workspace_provider().put(
            str(key),
            cast(dict[str, object], parsed),
            sub=str(sub_namespace) if sub_namespace else None,
        )
        return f"Stored {key}"

    def get(
        key: str,
        sub_namespace: str | None = None,
    ) -> str:
        """Retrieve the JSON value stored under the given key."""
        result = workspace_provider().get(
            str(key),
            sub=str(sub_namespace) if sub_namespace else None,
        )
        if result is None:
            return f"Key {key} not found"
        return json.dumps(result, ensure_ascii=True)

    def search(
        query: str | None = None,
        filter_json: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """Search items in the thread's workspace. Returns a JSON list."""
        filter_dict: dict[str, object] | None = None
        if filter_json:
            try:
                parsed = json.loads(str(filter_json))
                if isinstance(parsed, dict):
                    filter_dict = cast(dict[str, object], parsed)
            except json.JSONDecodeError:
                return "Error: filter_json must be a valid JSON object"
        results = workspace_provider().search(
            query=str(query) if query else None,
            filter=filter_dict,
            limit=max(1, int(limit)),
            offset=max(0, int(offset)),
        )
        return json.dumps(results, ensure_ascii=True)

    def delete(
        key: str,
        sub_namespace: str | None = None,
    ) -> str:
        """Delete an item from the thread's workspace."""
        workspace_provider().delete(
            str(key),
            sub=str(sub_namespace) if sub_namespace else None,
        )
        return f"Deleted {key}"

    return (
        tool_from_function(
            put,
            name="workspace_put",
            description=put.__doc__ or "",
            metadata={"service_component": "workspace"},
        ),
        tool_from_function(
            get,
            name="workspace_get",
            description=get.__doc__ or "",
            metadata={"service_component": "workspace"},
        ),
        tool_from_function(
            search,
            name="workspace_search",
            description=search.__doc__ or "",
            metadata={"service_component": "workspace"},
        ),
        tool_from_function(
            delete,
            name="workspace_delete",
            description=delete.__doc__ or "",
            metadata={"service_component": "workspace"},
        ),
    )
