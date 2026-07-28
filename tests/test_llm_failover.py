from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from nuself.llm import ChatMessage, LangChainLLMEndpoint, LLMSettings
from nuself.logs import read_log_events


def test_failover_llm_switches_and_remembers_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        assert isinstance(model, int)
        label = {0: "primary", 1: "backup"}[model]
        calls.append(label)
        if label == "primary":
            raise RuntimeError("LLM request failed with HTTP 400: InvalidSubscription")
        return f"ok:{label}"

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=cast(Any, 0)),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=cast(Any, 1)),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)
    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok:backup"
    assert calls == ["primary", "backup"]
    assert (tmp_path / "private" / "runtime" / "llm_state.json").read_text(encoding="utf-8") == (
        '{\n'
        '  "active_endpoint_index": 1,\n'
        '  "schema_version": 1\n'
        '}\n'
    )
    assert list(
        (tmp_path / "private" / "runtime").glob("*.tmp")
    ) == []
    logs = read_log_events(project_root=tmp_path, component="chat")
    assert logs[-1].event == "llm_endpoint_failed_over"
    assert logs[-1].status == "failed_over"
    assert logs[-1].metadata is not None
    assert logs[-1].metadata["next_endpoint_index"] == 1


def test_failover_llm_logs_unavailable_when_no_fallback_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        raise RuntimeError(
            'LLM request failed with HTTP 429: {"type":"error","error":{"type":"FreeUsageLimitError"}}'
        )

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("free-model"), model=cast(Any, 0)),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    with pytest.raises(RuntimeError, match="all configured LLM endpoints failed"):
        llm.complete([ChatMessage(role="user", content="hello")])

    logs = read_log_events(project_root=tmp_path, component="chat")
    assert len(logs) == 1
    assert logs[0].event == "llm_endpoint_unavailable"
    assert logs[0].status == "exhausted"
    assert logs[0].metadata is not None
    assert logs[0].metadata["endpoint_index"] == 0
    assert "next_endpoint_index" not in logs[0].metadata


def test_failover_llm_does_not_treat_longer_http_code_as_availability_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        calls.append(str(model))
        raise RuntimeError("LLM request failed with HTTP 4013: upstream bug")

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=cast(Any, 0)),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=cast(Any, 1)),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    with pytest.raises(RuntimeError, match="HTTP 4013"):
        llm.complete([ChatMessage(role="user", content="hello")])

    assert calls == ["0"]
    assert read_log_events(project_root=tmp_path, component="chat") == []


def test_failover_llm_starts_from_remembered_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "private" / "runtime" / "llm_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        '{"schema_version": 1, "active_endpoint_index": 1}\n',
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        calls.append(str(model))
        return "ok"

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=cast(Any, 0)),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=cast(Any, 1)),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok"
    assert calls == ["1"]


def test_endpoint_preference_diagnostics_cannot_discard_valid_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        return "valid response"

    def fail_state(*args: object, **kwargs: object) -> None:
        raise OSError("state store unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.llm._invoke_langchain_model",
        fake_invoke,
    )
    monkeypatch.setattr("nuself.llm._save_llm_state", fail_state)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    endpoints = (
        LangChainLLMEndpoint(
            index=0,
            settings=_endpoint_cfg("primary"),
            model=cast(Any, 0),
        ),
    )
    llm = _LangChainFailoverLLM(endpoints, project_root=tmp_path)

    with pytest.warns(
        RuntimeWarning,
        match=(
            "chat/llm_endpoint_state_write_failed: "
            "state store unavailable; structured logging failed: "
            "audit store unavailable"
        ),
    ):
        result = llm.complete(
            [ChatMessage(role="user", content="hello")]
        )

    assert result == "valid response"


def test_failover_llm_re_raises_non_availability_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        raise RuntimeError("some unrelated error")

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM  # pyright: ignore[reportPrivateUsage]

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=cast(Any, 0)),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=cast(Any, 1)),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    with pytest.raises(RuntimeError, match="some unrelated error"):
        llm.complete([ChatMessage(role="user", content="hello")])


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


def test_default_llm_loads_endpoint_state_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.llm as llm_module

    endpoints = (
        LangChainLLMEndpoint(
            index=0,
            settings=_endpoint_cfg("primary"),
            model=cast(Any, 0),
        ),
    )
    calls = 0

    def fake_load(
        project_root: Path | None,
        *,
        available_indices: set[int] | None = None,
    ) -> int | None:
        nonlocal calls
        assert project_root == tmp_path
        assert available_indices == {0}
        calls += 1
        return None

    def fake_endpoints(
        project_root: Path | None,
    ) -> tuple[LangChainLLMEndpoint, ...]:
        assert project_root == tmp_path
        return endpoints

    monkeypatch.setattr(
        llm_module,
        "_configured_llm_endpoints",
        fake_endpoints,
    )
    monkeypatch.setattr(llm_module, "_load_llm_state", fake_load)

    llm_module.default_llm(tmp_path)

    assert calls == 1


def _endpoint_cfg(model: str) -> LLMSettings:
    return LLMSettings(
        base_url=f"https://{model}.example/v1",
        api_key=f"{model}-key",
        model=model,
    )
