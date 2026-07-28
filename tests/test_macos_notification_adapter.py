"""Tests for MacOSNotificationAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nuself.logs import read_log_events
from nuself.notification import OutboxEntry
from nuself.notification.macos import MacOSNotificationAdapter


@pytest.fixture
def adapter(tmp_path: Path) -> MacOSNotificationAdapter:
    return MacOSNotificationAdapter(tmp_path, dry_run=True)


@pytest.fixture
def entry() -> OutboxEntry:
    return OutboxEntry(
        id="test-001",
        title="Test Title",
        body="Test body.",
        status="pending",
        idempotency_key="key-001",
    )


def test_dry_run_returns_true_and_logs(adapter: MacOSNotificationAdapter, entry: OutboxEntry) -> None:
    assert adapter.send(entry) is True
    [event] = read_log_events(
        project_root=adapter._project_root,  # pyright: ignore[reportPrivateUsage]
        component="outbox",
    )
    assert event.event == "macos_dry_run"
    assert event.status == "simulated"
    assert event.metadata == {"entry_id": "test-001", "attempt": 0}
    assert "Test Title" not in event.message
    assert "Test body." not in event.message
    assert "key-001" not in str(event.metadata)


def test_unavailable_osascript_returns_true_and_logs(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = False
    assert adapter.send(entry) is True


def test_send_runs_osascript(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = True

    with patch("nuself.notification.macos.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        assert adapter.send(entry) is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "display notification" in args[2]
        assert "Test Title" in args[2]


def test_send_osascript_failure_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = True

    with patch("nuself.notification.macos.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="execution error")
        assert adapter.send(entry) is False


def test_osascript_failure_diagnostic_preserves_false(
    tmp_path: Path,
    entry: OutboxEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = True

    with patch("nuself.notification.macos.subprocess.run") as run:
        run.return_value = MagicMock(
            returncode=1,
            stderr="execution error",
        )
        with pytest.warns(
            RuntimeWarning,
            match=(
                "outbox/macos_failed: execution error; "
                "structured logging failed: audit store unavailable"
            ),
        ):
            result = adapter.send(entry)

    assert result is False


def test_send_osascript_timeout_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    import subprocess

    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = True

    with patch("nuself.notification.macos.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=10)
        assert adapter.send(entry) is False


def test_osascript_timeout_diagnostic_preserves_false(
    tmp_path: Path,
    entry: OutboxEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    adapter = MacOSNotificationAdapter(tmp_path, dry_run=False)
    adapter.has_osascript = True

    with patch("nuself.notification.macos.subprocess.run") as run:
        run.side_effect = subprocess.TimeoutExpired(
            cmd="osascript",
            timeout=10,
        )
        with pytest.warns(
            RuntimeWarning,
            match=(
                "outbox/macos_failed: osascript timed out; "
                "structured logging failed: audit store unavailable"
            ),
        ):
            result = adapter.send(entry)

    assert result is False


def test_escape_quotes() -> None:
    assert MacOSNotificationAdapter.escape('say "hello"') == '"say \\"hello\\""'


def test_escape_backslash() -> None:
    assert MacOSNotificationAdapter.escape("path\\to\\file") == '"path\\\\to\\\\file"'
