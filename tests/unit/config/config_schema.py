from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def test_config_json_schema_uses_direct_llm_endpoint_list() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "nuself-config.schema.json"
    )
    schema = cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))
    properties = cast(dict[str, Any], schema["properties"])
    llm_schema = cast(dict[str, Any], properties["llm"])
    endpoint_schema = cast(dict[str, Any], llm_schema["items"])
    endpoint_properties = cast(dict[str, Any], endpoint_schema["properties"])

    assert llm_schema["type"] == "array"
    assert "openai" not in llm_schema
    assert "openai" not in endpoint_properties
    assert endpoint_properties["anthropic"]["type"] == "boolean"
    assert endpoint_properties["timeout_seconds"]["default"] == 60
    assert endpoint_properties["base_url"]["default"] == "https://api.openai.com/v1"
    assert "https://api.anthropic.com API root" in (
        endpoint_properties["base_url"]["description"]
    )
    examples = cast(list[list[dict[str, object]]], llm_schema["examples"])
    assert examples[0][1]["base_url"] == "https://api.anthropic.com"


def test_config_json_schema_exposes_chat_request_timeout() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "nuself-config.schema.json"
    )
    schema = cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))
    properties = cast(dict[str, Any], schema["properties"])
    chat_schema = cast(dict[str, Any], properties["chat"])
    chat_properties = cast(dict[str, Any], chat_schema["properties"])

    assert chat_properties["request_timeout_seconds"]["default"] == 120


def test_experimental_schema_has_no_removed_langmem_runtime() -> None:
    root = Path(__file__).resolve().parents[3]
    schema = cast(
        dict[str, Any],
        json.loads(
            (root / "docs" / "nuself-config.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    properties = cast(dict[str, Any], schema["properties"])
    experimental = cast(dict[str, Any], properties["experimental"])
    experimental_properties = cast(
        dict[str, Any],
        experimental["properties"],
    )

    assert set(experimental_properties) == {"vector_index"}
    assert "langmem_adapter" not in (
        root / "examples" / "private" / "config.yaml"
    ).read_text(encoding="utf-8")
