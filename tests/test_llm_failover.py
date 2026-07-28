from __future__ import annotations

from pathlib import Path
import pytest

from nuself.logs import read_log_events


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        '{"active_endpoint_index": 1}',
        '{"schema_version": 1, "active_endpoint_index": true}',
        '{"schema_version": 1, "active_endpoint_index": -1}',
        '{"schema_version": 2, "active_endpoint_index": 1}',
    ],
)
def test_invalid_endpoint_state_is_observable_and_uses_config_order(
    tmp_path: Path,
    raw: str,
) -> None:
    from nuself.llm import _load_llm_state  # pyright: ignore[reportPrivateUsage]

    state_path = tmp_path / "private" / "runtime" / "llm_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(raw, encoding="utf-8")

    assert _load_llm_state(
        tmp_path,
        available_indices={0, 1},
    ) is None
    logs = read_log_events(project_root=tmp_path, component="chat")
    assert len(logs) == 1
    assert logs[0].event == "record_decode_failed"
    assert logs[0].status == "degraded"
    assert logs[0].metadata == {
        "collection": "llm_endpoint_state",
        "record_id": "llm_state",
    }
    assert raw not in (logs[0].error or "")


def test_stale_endpoint_state_is_observable_and_uses_config_order(
    tmp_path: Path,
) -> None:
    from nuself.llm import _load_llm_state  # pyright: ignore[reportPrivateUsage]

    state_path = tmp_path / "private" / "runtime" / "llm_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        '{"schema_version": 1, "active_endpoint_index": 2}',
        encoding="utf-8",
    )

    assert _load_llm_state(
        tmp_path,
        available_indices={0, 1},
    ) is None
    logs = read_log_events(project_root=tmp_path, component="chat")
    assert logs[-1].event == "record_decode_failed"


@pytest.mark.parametrize("index", [-1, True])
def test_invalid_endpoint_state_is_not_written(
    tmp_path: Path,
    index: int,
) -> None:
    from nuself.llm import _save_llm_state  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(ValueError, match="non-negative integer"):
        _save_llm_state(tmp_path, index)
    assert not (
        tmp_path / "private" / "runtime" / "llm_state.json"
    ).exists()
