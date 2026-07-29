from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from nuself.config import (
    ChatConfig,
    ChatContextConfig,
    DaemonConfig,
    DaemonMemoryCuratorConfig,
    DaemonNotificationDeliveryConfig,
    DaemonReasonSchedulerConfig,
    DaemonReflectionSchedulerConfig,
    EmailConfig,
    EmailSmtpConfig,
    ExperimentalConfig,
    LlmEndpointConfig,
    MacosNotificationConfig,
    ReflectionDiscussionConfig,
    ReflectionGateConfig,
    ReflectionModeratorConfig,
    ReflectionSchedulerConfig,
    ReflectionSettings,
    SystemConfig,
)


ROOT = Path(__file__).resolve().parents[3]


def _published_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "docs" / "nuself-config.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def _object_at(
    root: dict[str, Any],
    *path: str,
) -> dict[str, Any]:
    current = root
    for name in path:
        properties = cast(dict[str, Any], current["properties"])
        current = cast(dict[str, Any], properties[name])
    return current


def _resolve_ref(
    root: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    ref = value.get("$ref")
    if not isinstance(ref, str):
        return value
    current: Any = root
    for component in ref.removeprefix("#/").split("/"):
        current = current[component]
    return cast(dict[str, Any], current)


def _assert_model_object_parity(
    model: type[BaseModel],
    published: dict[str, Any],
) -> None:
    runtime = model.model_json_schema()
    runtime_properties = cast(dict[str, Any], runtime["properties"])
    published_properties = cast(dict[str, Any], published["properties"])

    assert set(published_properties) == set(runtime_properties)
    assert published["additionalProperties"] is False
    assert runtime["additionalProperties"] is False
    for name, runtime_raw in runtime_properties.items():
        runtime_property = _resolve_ref(
            runtime,
            cast(dict[str, Any], runtime_raw),
        )
        published_property = cast(
            dict[str, Any],
            published_properties[name],
        )
        for keyword in (
            "type",
            "default",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
        ):
            if keyword in runtime_property:
                assert published_property.get(keyword) == (
                    runtime_property[keyword]
                ), f"{model.__name__}.{name}.{keyword}"


def test_runtime_models_and_published_schema_have_complete_parity() -> None:
    schema = _published_schema()
    top_properties = cast(dict[str, Any], schema["properties"])
    assert set(top_properties) == set(SystemConfig.model_fields)
    assert schema["additionalProperties"] is False

    pairs: tuple[tuple[type[BaseModel], dict[str, Any]], ...] = (
        (LlmEndpointConfig, cast(dict[str, Any], top_properties["llm"])["items"]),
        (ChatConfig, _object_at(schema, "chat")),
        (ChatContextConfig, _object_at(schema, "chat", "context")),
        (DaemonConfig, _object_at(schema, "daemon")),
        (
            DaemonMemoryCuratorConfig,
            _object_at(schema, "daemon", "memory_curator"),
        ),
        (
            DaemonReflectionSchedulerConfig,
            _object_at(schema, "daemon", "reflection_scheduler"),
        ),
        (
            DaemonNotificationDeliveryConfig,
            _object_at(schema, "daemon", "notification_delivery"),
        ),
        (
            DaemonReasonSchedulerConfig,
            _object_at(schema, "daemon", "reason_scheduler"),
        ),
        (ReflectionSettings, _object_at(schema, "reflection")),
        (
            ReflectionSchedulerConfig,
            _object_at(schema, "reflection", "scheduler"),
        ),
        (
            ReflectionGateConfig,
            _object_at(schema, "reflection", "gate"),
        ),
        (
            ReflectionModeratorConfig,
            _object_at(schema, "reflection", "moderator"),
        ),
        (
            ReflectionDiscussionConfig,
            _object_at(schema, "reflection", "discussion"),
        ),
        (EmailConfig, _object_at(schema, "email")),
        (EmailSmtpConfig, _object_at(schema, "email", "smtp")),
        (
            MacosNotificationConfig,
            _object_at(schema, "macos_notification"),
        ),
        (ExperimentalConfig, _object_at(schema, "experimental")),
    )
    for model, published in pairs:
        _assert_model_object_parity(model, published)

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
    assert endpoint_properties["base_url"]["default"] == ""
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
