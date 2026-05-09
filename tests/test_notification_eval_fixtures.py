"""Evaluation fixtures for proactive notification behavior."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from nuself.notification import NotificationOutbox, OutboxEntry
from nuself.notification.deep_link import DeepLink
from nuself.reflection import ReflectionScheduler, ReflectionSettings


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "notifications"


def _load_json(path: Path) -> dict[str, object]:
    import json

    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"fixture must be an object: {path}")
    return cast(dict[str, object], raw)


def test_reflection_scheduler_fixture() -> None:
    data = _load_json(FIXTURES_DIR / "reflection_scheduler.json")
    settings_raw = data.get("settings")
    assert isinstance(settings_raw, dict)
    settings_data = cast(dict[str, object], settings_raw)
    settings = ReflectionSettings(
        interval_seconds=int(cast(Any, settings_data.get("interval_seconds", 3600))),
        cooldown_seconds=int(cast(Any, settings_data.get("cooldown_seconds", 300))),
        quiet_start_hour=int(cast(Any, settings_data.get("quiet_start_hour", 22))),
        quiet_end_hour=int(cast(Any, settings_data.get("quiet_end_hour", 7))),
        daily_cap=int(cast(Any, settings_data.get("daily_cap", 5))),
        jitter_percent=int(cast(Any, settings_data.get("jitter_percent", 20))),
    )

    scenarios_raw = data.get("scenarios")
    assert isinstance(scenarios_raw, list)
    scenarios = cast(list[object], scenarios_raw)
    for scenario_raw in scenarios:
        assert isinstance(scenario_raw, dict)
        scenario = cast(dict[str, object], scenario_raw)
        name = str(scenario.get("name"))
        last_raw = scenario.get("last_reflection")
        last = datetime.fromisoformat(str(last_raw)) if last_raw is not None else None
        now = datetime.fromisoformat(str(scenario.get("now")))
        expected = bool(scenario.get("expected_should_reflect"))

        scheduler = ReflectionScheduler.__new__(ReflectionScheduler)
        scheduler._settings = settings  # pyright: ignore[reportPrivateUsage]
        scheduler._last_reflection_path = Path("/dev/null")  # pyright: ignore[reportPrivateUsage]
        scheduler._event_queue = []  # pyright: ignore[reportPrivateUsage]
        if last is not None:
            scheduler._write_last_reflection = lambda now: None  # type: ignore[method-assign]  # pyright: ignore[reportUnknownLambdaType]
            # Monkey-patch _read_last_reflection for this test
            scheduler._read_last_reflection = lambda: last  # type: ignore[method-assign]  # pyright: ignore[reportUnknownLambdaType]
        else:
            scheduler._read_last_reflection = lambda: None  # type: ignore[method-assign]  # pyright: ignore[reportUnknownLambdaType]

        actual = scheduler.should_reflect(now)
        assert actual == expected, f"scenario {name}: expected {expected}, got {actual}"


def test_deep_link_fixture() -> None:
    data = _load_json(FIXTURES_DIR / "deep_link.json")
    scenarios_raw = data.get("scenarios")
    assert isinstance(scenarios_raw, list)
    scenarios = cast(list[object], scenarios_raw)
    for scenario_raw in scenarios:
        assert isinstance(scenario_raw, dict)
        scenario = cast(dict[str, object], scenario_raw)
        name = str(scenario.get("name"))
        url = str(scenario.get("url"))
        should_succeed = bool(scenario.get("should_succeed"))

        if should_succeed:
            link = DeepLink.parse(url)
            expected_thread = str(scenario.get("expected_thread_id"))
            expected_message = scenario.get("expected_message")
            assert link.thread_id == expected_thread, f"scenario {name} thread_id"
            if expected_message is not None:
                assert link.message == str(expected_message), f"scenario {name} message"
        else:
            with pytest.raises(ValueError):
                DeepLink.parse(url)


def test_outbox_delivery_fixture(tmp_path: Path) -> None:
    data = _load_json(FIXTURES_DIR / "outbox_delivery.json")
    scenarios_raw = data.get("scenarios")
    assert isinstance(scenarios_raw, list)
    scenarios = cast(list[object], scenarios_raw)
    for scenario_raw in scenarios:
        assert isinstance(scenario_raw, dict)
        scenario = cast(dict[str, object], scenario_raw)
        name = str(scenario.get("name"))
        outbox_dir = tmp_path / "outbox" / name
        outbox_dir.mkdir(parents=True, exist_ok=True)
        outbox = NotificationOutbox.__new__(NotificationOutbox)
        outbox._outbox_dir = outbox_dir  # pyright: ignore[reportPrivateUsage]

        actions_raw = scenario.get("actions")
        assert isinstance(actions_raw, list)
        actions = cast(list[object], actions_raw)
        for action_raw in actions:
            assert isinstance(action_raw, dict)
            action = cast(dict[str, object], action_raw)
            act = str(action.get("action"))
            if act == "add":
                entry_raw = action.get("entry")
                assert isinstance(entry_raw, dict)
                entry_data = cast(dict[str, object], entry_raw)
                outbox.add(
                    OutboxEntry(
                        id=str(entry_data.get("id")),
                        title=str(entry_data.get("title")),
                        body=str(entry_data.get("body")),
                        status="pending",  # type: ignore[arg-type]
                        idempotency_key=str(entry_data.get("idempotency_key")),
                    )
                )
            elif act == "mark_sent":
                outbox.mark_sent(str(action.get("entry_id")))

        expected_pending = scenario.get("expected_list_pending")
        expected_sent = scenario.get("expected_list_sent")
        assert isinstance(expected_pending, list)
        assert isinstance(expected_sent, list)

        pending_ids = [e.id for e in outbox.list(status="pending")]
        sent_ids = [e.id for e in outbox.list(status="sent")]

        assert pending_ids == [str(x) for x in cast(list[object], expected_pending)], f"scenario {name} pending"
        assert sent_ids == [str(x) for x in cast(list[object], expected_sent)], f"scenario {name} sent"
