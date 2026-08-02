from __future__ import annotations

from pathlib import Path
import pytest

from nuself.log.reader import read_log_events
from nuself.llm import LLMSettings, build_langchain_endpoint


def test_llm_settings_repr_excludes_api_key() -> None:
    secret = "provider-secret-value"
    settings = LLMSettings(
        base_url="https://example.invalid/v1",
        api_key=secret,
        model="example",
    )

    assert secret not in repr(settings)
    assert "api_key" not in repr(settings)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "https://api.anthropic.com",
            "https://api.anthropic.com",
        ),
        (
            "https://api.anthropic.com/v1",
            "https://api.anthropic.com",
        ),
        (
            "https://opencode.ai/zen/go/v1/",
            "https://opencode.ai/zen/go",
        ),
    ],
)
def test_anthropic_sdk_base_url_uses_api_root(
    configured: str,
    expected: str,
) -> None:
    from nuself.llm import _anthropic_sdk_base_url  # pyright: ignore[reportPrivateUsage]

    assert _anthropic_sdk_base_url(configured) == expected


def test_anthropic_endpoint_disables_thinking_for_forced_tools() -> None:
    endpoint = build_langchain_endpoint(
        0,
        LLMSettings(
            base_url="https://example.invalid/v1",
            api_key="test",
            model="example",
            provider="anthropic",
        ),
    )

    assert getattr(endpoint.model, "thinking") == {
        "type": "disabled",
    }


@pytest.mark.parametrize(
    ("message", "secret", "expected_fragment"),
    [
        (
            "request failed api_key=sk-super-secret",
            "sk-super-secret",
            "api_key=***",
        ),
        (
            'provider rejected {"password": "hunter2"}',
            "hunter2",
            '"password": "***"',
        ),
        (
            "Authorization: Bearer abc.def-123",
            "abc.def-123",
            "Authorization: ***",
        ),
        (
            "https://provider.invalid?access_token=query-secret&model=x",
            "query-secret",
            "access_token=***&model=x",
        ),
        (
            "provider returned key sk-proj-1234567890abcdef",
            "sk-proj-1234567890abcdef",
            "provider returned key ***",
        ),
        (
            "anthropic key sk-ant-api03-1234567890abcdef",
            "sk-ant-api03-1234567890abcdef",
            "anthropic key ***",
        ),
        (
            "observer received xoxb-1234567890-secret",
            "xoxb-1234567890-secret",
            "observer received ***",
        ),
        (
            "adapter returned ghp_1234567890abcdef",
            "ghp_1234567890abcdef",
            "adapter returned ***",
        ),
        (
            "cloud response AKIAIOSFODNN7EXAMPLE",
            "AKIAIOSFODNN7EXAMPLE",
            "cloud response ***",
        ),
    ],
)
def test_llm_error_redaction_removes_credentials(
    message: str,
    secret: str,
    expected_fragment: str,
) -> None:
    from nuself.llm import redact_llm_error

    redacted = redact_llm_error(message)

    assert secret not in redacted
    assert expected_fragment in redacted


def test_llm_error_redaction_happens_before_length_bound() -> None:
    from nuself.llm import redact_llm_error

    secret = "provider-secret-value"
    message = f"{'x' * 480} api_key={secret} {'tail' * 40}"

    redacted = redact_llm_error(message)

    assert secret not in redacted
    assert "api_key=***" in redacted
    assert len(redacted) == 500
    assert redacted.endswith("...")


def test_llm_error_redaction_survives_broken_exception_renderer() -> None:
    from nuself.llm import redact_llm_error

    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise KeyboardInterrupt

    assert redact_llm_error(BrokenMessageError()) == "BrokenMessageError"


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

    state_path = tmp_path / "runtime" / "llm_state.json"
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

    state_path = tmp_path / "runtime" / "llm_state.json"
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
        tmp_path / "runtime" / "llm_state.json"
    ).exists()
