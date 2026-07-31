"""Structured local evaluators for notification-related fixtures."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import cast

from nuself.config import (
    ReflectionDiscussionConfig,
    ReflectionGateConfig,
    ReflectionModeratorConfig,
    ReflectionSchedulerConfig,
    ReflectionSettings,
    runtime_paths,
)
from nuself.eval import EvalResult
from nuself.notification import NotificationOutbox, OutboxEntry
from nuself.notification.deep_link import DeepLink
from nuself.reflection import ReflectionScheduler
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.storage import auto_backend


def run_notification_eval(
    project_root: Path,
    fixtures_dir: Path,
) -> list[EvalResult]:
    """Return one structured result for every notification scenario."""
    results: list[EvalResult] = []
    for path in sorted(fixtures_dir.glob("*.json")):
        fixture = _load_fixture(path)
        component = _required_str(fixture, "component")
        scenarios = _required_objects(fixture, "scenarios")
        for scenario in scenarios:
            name = (
                f"{path.stem}/"
                f"{_required_str(scenario, 'name')}"
            )
            try:
                if component == "deep_link":
                    _evaluate_deep_link(scenario)
                elif component == "notification_outbox":
                    _evaluate_outbox(
                        project_root / path.stem / name.replace("/", "-"),
                        scenario,
                    )
                elif component == "reflection_scheduler":
                    _evaluate_scheduler(
                        project_root / path.stem / name.replace("/", "-"),
                        fixture,
                        scenario,
                    )
                else:
                    raise ValueError(
                        f"unknown notification eval component: {component}"
                    )
            except Exception as exc:
                results.append(
                    EvalResult(
                        fixture_name=name,
                        passed=False,
                        score=0.0,
                        failures=(diagnostic_exception_message(exc),),
                    )
                )
            else:
                results.append(
                    EvalResult(
                        fixture_name=name,
                        passed=True,
                        score=1.0,
                        failures=(),
                    )
                )
    return results


def _evaluate_deep_link(scenario: dict[str, object]) -> None:
    url = _required_str(scenario, "url")
    should_succeed = _required_bool(scenario, "should_succeed")
    if not should_succeed:
        try:
            DeepLink.parse(url)
        except ValueError:
            return
        raise AssertionError("expected deep link parsing to fail")

    link = DeepLink.parse(url)
    expected_conversation = _required_str(
        scenario,
        "expected_conversation_id",
    )
    if link.conversation_id != expected_conversation:
        raise AssertionError(
            f"conversation_id {link.conversation_id!r} != {expected_conversation!r}"
        )
    expected_message = scenario.get("expected_message")
    if link.message != expected_message:
        raise AssertionError(
            f"message {link.message!r} != {expected_message!r}"
        )


def _evaluate_scheduler(
    project_root: Path,
    fixture: dict[str, object],
    scenario: dict[str, object],
) -> None:
    settings_data = _required_object(fixture, "settings")
    settings = ReflectionSettings(
        scheduler=ReflectionSchedulerConfig(
            interval_seconds=_int_value(
                settings_data,
                "interval_seconds",
                3600,
            ),
            cooldown_seconds=_int_value(
                settings_data,
                "cooldown_seconds",
                300,
            ),
            quiet_start_hour=_int_value(
                settings_data,
                "quiet_start_hour",
                22,
            ),
            quiet_end_hour=_int_value(
                settings_data,
                "quiet_end_hour",
                7,
            ),
            daily_cap=_int_value(settings_data, "daily_cap", 5),
            jitter_percent=_int_value(
                settings_data,
                "jitter_percent",
                20,
            ),
        ),
        gate=ReflectionGateConfig(
            relevance_threshold=0.5,
            persona_discussion_threshold=1.0,
        ),
        moderator=ReflectionModeratorConfig(
            max_discussion_rounds=2,
            moderator_convergence_patience=1,
        ),
        discussion=ReflectionDiscussionConfig(),
    )
    last_raw = scenario.get("last_reflection")
    last = (
        datetime.fromisoformat(str(last_raw))
        if last_raw is not None
        else None
    )
    now = datetime.fromisoformat(_required_str(scenario, "now"))
    scheduler = ReflectionScheduler.__new__(ReflectionScheduler)
    scheduler._config = settings  # pyright: ignore[reportPrivateUsage]
    project_root.mkdir(parents=True, exist_ok=True)
    scheduler._project_root = project_root  # pyright: ignore[reportPrivateUsage]
    scheduler._schedule_collection = auto_backend(  # pyright: ignore[reportPrivateUsage]
        project_root
    ).collection("scheduler_state")
    if last is not None:
        scheduler._write_last_reflection(last)  # pyright: ignore[reportPrivateUsage]
    actual = scheduler.should_reflect(now)
    expected = _required_bool(
        scenario,
        "expected_should_reflect",
    )
    if actual is not expected:
        raise AssertionError(
            f"should_reflect {actual!r} != {expected!r}"
        )


def _evaluate_outbox(
    storage_root: Path,
    scenario: dict[str, object],
) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    outbox = NotificationOutbox(
        runtime_paths(storage_root),
        auto_backend(storage_root),
    )
    for action in _required_objects(scenario, "actions"):
        action_name = _required_str(action, "action")
        if action_name == "add":
            entry = _required_object(action, "entry")
            outbox.add(
                OutboxEntry(
                    id=_required_str(entry, "id"),
                    title=_required_str(entry, "title"),
                    body=_required_str(entry, "body"),
                    status="pending",
                    idempotency_key=_required_str(
                        entry,
                        "idempotency_key",
                    ),
                )
            )
        elif action_name == "deliver_success":
            entry_id = _required_str(action, "entry_id")
            outbox.prepare_delivery(entry_id, ("eval",))
            outbox.begin_adapter_delivery(entry_id, "eval")
            outbox.record_adapter_result(
                entry_id,
                "eval",
                success=True,
            )
            outbox.finalize_delivery(entry_id)
        else:
            raise ValueError(f"unknown outbox action: {action_name}")

    pending = [entry.id for entry in outbox.list(status="pending")]
    sent = [entry.id for entry in outbox.list(status="sent")]
    expected_pending = _required_strings(
        scenario,
        "expected_list_pending",
    )
    expected_sent = _required_strings(
        scenario,
        "expected_list_sent",
    )
    if pending != expected_pending:
        raise AssertionError(
            f"pending ids {pending!r} != {expected_pending!r}"
        )
    if sent != expected_sent:
        raise AssertionError(
            f"sent ids {sent!r} != {expected_sent!r}"
        )


def _load_fixture(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"fixture must contain an object: {path}")
    return cast(dict[str, object], raw)


def _required_object(
    data: dict[str, object],
    field_name: str,
) -> dict[str, object]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object")
    return cast(dict[str, object], value)


def _required_objects(
    data: dict[str, object],
    field_name: str,
) -> list[dict[str, object]]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(
                f"field '{field_name}' must contain objects"
            )
        result.append(cast(dict[str, object], item))
    return result


def _required_str(
    data: dict[str, object],
    field_name: str,
) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _required_bool(
    data: dict[str, object],
    field_name: str,
) -> bool:
    value = data.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a boolean")
    return value


def _required_strings(
    data: dict[str, object],
    field_name: str,
) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(
                f"field '{field_name}' must contain strings"
            )
        result.append(item)
    return result


def _int_value(
    data: dict[str, object],
    field_name: str,
    default: int,
) -> int:
    value = data.get(field_name, default)
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer")
    return value
