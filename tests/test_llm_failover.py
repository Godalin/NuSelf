from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nuself.llm import ChatMessage, LangChainLLMEndpoint, LLMSettings, default_llm
from nuself.logs import read_log_events


def _lc_endpoint(index: int, model: str) -> LangChainLLMEndpoint:
    return LangChainLLMEndpoint(
        index=index,
        settings=LLMSettings(
            base_url=f"https://{model}.example/v1",
            api_key=f"{model}-key",
            model=model,
        ),
        model=index,  # placeholder; will be replaced by monkeypatched _invoke
    )


class _FakeModel:
    """A fake ``BaseChatModel`` that delegates to a user-provided callable."""

    def __init__(self, invoke_fn: Any) -> None:
        self._invoke_fn = invoke_fn

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        return self._invoke_fn(messages, **kwargs)


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
    from nuself.llm import _LangChainFailoverLLM

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=0),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=1),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)
    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok:backup"
    assert calls == ["primary", "backup"]
    assert (tmp_path / "private" / "runtime" / "llm_state.json").read_text(encoding="utf-8") == (
        '{"active_endpoint_index": 1}\n'
    )
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
    from nuself.llm import _LangChainFailoverLLM

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("free-model"), model=0),
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
    from nuself.llm import _LangChainFailoverLLM

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=0),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=1),
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
    state_path.write_text('{"active_endpoint_index": 1}\n', encoding="utf-8")
    calls: list[str] = []

    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        calls.append(str(model))
        return "ok"

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=0),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=1),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok"
    assert calls == ["1"]


def test_failover_llm_re_raises_non_availability_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_invoke(model: object, messages: list[ChatMessage]) -> str:
        raise RuntimeError("some unrelated error")

    monkeypatch.setattr("nuself.llm._invoke_langchain_model", fake_invoke)
    from nuself.llm import _LangChainFailoverLLM

    eps = (
        LangChainLLMEndpoint(index=0, settings=_endpoint_cfg("primary"), model=0),
        LangChainLLMEndpoint(index=1, settings=_endpoint_cfg("backup"), model=1),
    )
    llm = _LangChainFailoverLLM(eps, project_root=tmp_path)

    with pytest.raises(RuntimeError, match="some unrelated error"):
        llm.complete([ChatMessage(role="user", content="hello")])


def _endpoint_cfg(model: str) -> LLMSettings:
    return LLMSettings(
        base_url=f"https://{model}.example/v1",
        api_key=f"{model}-key",
        model=model,
    )
