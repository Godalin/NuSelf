"""Tests for MacOSNotificationAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_escape_quotes() -> None:
    assert MacOSNotificationAdapter.escape('say "hello"') == '"say \\"hello\\""'


def test_escape_backslash() -> None:
    assert MacOSNotificationAdapter.escape("path\\to\\file") == '"path\\\\to\\\\file"'
