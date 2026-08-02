"""Workspace-owned framework tool definitions."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import cast

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, mutating, observed, readonly, tool
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.store import ScopedWorkspace


def build_workspace_tools_from_provider(
    workspace_provider: Callable[[], ScopedWorkspace],
) -> tuple[BaseTool, ...]:
    """Build workspace tools that resolve the active workspace lazily."""
    executor = FeatureExecutor()

    @tool(name="workspace_put", description="Store a JSON value under the given key in the thread's workspace.")
    @component("workspace")
    @mutating
    @observed
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

    @tool(name="workspace_get", description="Retrieve the JSON value stored under the given key.")
    @component("workspace")
    @readonly
    @observed
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

    @tool(name="workspace_search", description="Search items in the thread's workspace. Returns a JSON list.")
    @component("workspace")
    @readonly
    @observed
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

    @tool(name="workspace_delete", description="Delete an item from the thread's workspace.")
    @component("workspace")
    @mutating
    @observed
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
        materialize_tool(put, executor=executor),
        materialize_tool(get, executor=executor),
        materialize_tool(search, executor=executor),
        materialize_tool(delete, executor=executor),
    )
