from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from nuself.llm import ChatMessage, FailoverLLM, LLMEndpoint, LLMSettings
from nuself.logs import read_log_events


def _endpoint(index: int, model: str, *, provider: Literal["openai", "anthropic"] = "openai") -> LLMEndpoint:
    return LLMEndpoint(
        index=index,
        settings=LLMSettings(
            base_url=f"https://{model}.example/v1",
            api_key=f"{model}-key",
            model=model,
            provider=provider,
        ),
    )


def test_failover_llm_switches_and_remembers_success(
    tmp_path: Path, monkeypatch: object
) -> None:
    calls: list[str] = []

    def fake_complete(self: object, messages: list[ChatMessage]) -> str:
        settings = getattr(self, "_settings")
        model = getattr(settings, "model")
        calls.append(model)
        if model == "primary":
            raise RuntimeError("LLM request failed with HTTP 400: InvalidSubscription")
        return f"ok:{model}"

    monkeypatch.setattr("nuself.llm.OpenAICompatibleLLM.complete", fake_complete)  # type: ignore[attr-defined]
    llm = FailoverLLM((_endpoint(0, "primary"), _endpoint(1, "backup")), project_root=tmp_path)

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
    tmp_path: Path, monkeypatch: object
) -> None:
    def fake_complete(self: object, messages: list[ChatMessage]) -> str:
        raise RuntimeError(
            'LLM request failed with HTTP 429: {"type":"error","error":{"type":"FreeUsageLimitError"}}'
        )

    monkeypatch.setattr("nuself.llm.OpenAICompatibleLLM.complete", fake_complete)  # type: ignore[attr-defined]
    llm = FailoverLLM((_endpoint(0, "free-model"),), project_root=tmp_path)

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
    tmp_path: Path, monkeypatch: object
) -> None:
    calls: list[str] = []

    def fake_complete(self: object, messages: list[ChatMessage]) -> str:
        settings = getattr(self, "_settings")
        calls.append(getattr(settings, "model"))
        raise RuntimeError("LLM request failed with HTTP 4013: upstream bug")

    monkeypatch.setattr("nuself.llm.OpenAICompatibleLLM.complete", fake_complete)  # type: ignore[attr-defined]
    llm = FailoverLLM((_endpoint(0, "primary"), _endpoint(1, "backup")), project_root=tmp_path)

    with pytest.raises(RuntimeError, match="HTTP 4013"):
        llm.complete([ChatMessage(role="user", content="hello")])

    assert calls == ["primary"]
    assert read_log_events(project_root=tmp_path, component="chat") == []


def test_failover_llm_starts_from_remembered_success(
    tmp_path: Path, monkeypatch: object
) -> None:
    state_path = tmp_path / "private" / "runtime" / "llm_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"active_endpoint_index": 1}\n', encoding="utf-8")
    calls: list[str] = []

    def fake_complete(self: object, messages: list[ChatMessage]) -> str:
        settings = getattr(self, "_settings")
        model = getattr(settings, "model")
        calls.append(model)
        return f"ok:{model}"

    monkeypatch.setattr("nuself.llm.OpenAICompatibleLLM.complete", fake_complete)  # type: ignore[attr-defined]
    llm = FailoverLLM((_endpoint(0, "primary"), _endpoint(1, "backup")), project_root=tmp_path)

    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok:backup"
    assert calls == ["backup"]


def test_failover_llm_dispatches_anthropic_endpoint(
    tmp_path: Path, monkeypatch: object
) -> None:
    calls: list[str] = []

    def fake_anthropic_complete(self: object, messages: list[ChatMessage]) -> str:
        settings = getattr(self, "_settings")
        model = getattr(settings, "model")
        calls.append(model)
        return f"ok:{model}"

    monkeypatch.setattr("nuself.llm.AnthropicLLM.complete", fake_anthropic_complete)  # type: ignore[attr-defined]
    llm = FailoverLLM((_endpoint(0, "claude", provider="anthropic"),), project_root=tmp_path)

    result = llm.complete([ChatMessage(role="user", content="hello")])

    assert result == "ok:claude"
    assert calls == ["claude"]


def test_failover_llm_uses_endpoint_timeout(
    tmp_path: Path, monkeypatch: object
) -> None:
    captured_timeout = 0.0

    def fake_complete(self: object, messages: list[ChatMessage]) -> str:
        settings = getattr(self, "_settings")
        nonlocal captured_timeout
        captured_timeout = getattr(settings, "timeout_seconds")
        return "ok"

    monkeypatch.setattr("nuself.llm.OpenAICompatibleLLM.complete", fake_complete)  # type: ignore[attr-defined]
    endpoint = LLMEndpoint(
        index=0,
        settings=LLMSettings(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="deepseek-r1",
            timeout_seconds=300,
        ),
    )
    llm = FailoverLLM((endpoint,), project_root=tmp_path)

    assert llm.complete([ChatMessage(role="user", content="hello")]) == "ok"
    assert captured_timeout == 300
