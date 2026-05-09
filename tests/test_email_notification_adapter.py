"""Tests for EmailNotificationAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nuself.notification import OutboxEntry
from nuself.notification.email import EmailNotificationAdapter


@pytest.fixture
def entry() -> OutboxEntry:
    return OutboxEntry(
        id="test-001",
        title="Test Title",
        body="Test body.",
        status="pending",
        idempotency_key="key-001",
    )


def _write_config(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[smtp]\nhost = "smtp.example.com"\nport = 587\nuser = "u"\npassword = "p"\n\n'
        '[notification]\nfrom = "nuself@localhost"\nto = "user@example.com"\n',
        encoding="utf-8",
    )


def test_dry_run_returns_true_and_logs(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = EmailNotificationAdapter(tmp_path, dry_run=True)
    assert adapter.send(entry) is True


def test_no_config_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
    assert adapter.send(entry) is False


def test_send_with_config(tmp_path: Path, entry: OutboxEntry) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_server.__enter__ = lambda self: self
        mock_server.__exit__ = lambda self, *args: None
        mock_smtp_cls.return_value = mock_server
        assert adapter.send(entry) is True
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("u", "p")
        mock_server.send_message.assert_called_once()


def test_send_failure_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("network error")
        assert adapter.send(entry) is False


def test_send_without_auth(tmp_path: Path, entry: OutboxEntry) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[smtp]\nhost = "smtp.example.com"\nport = 25\n\n'
        '[notification]\nfrom = "nuself@localhost"\nto = "user@example.com"\n',
        encoding="utf-8",
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        assert adapter.send(entry) is True
        mock_server.login.assert_not_called()


def test_load_config_ignores_invalid_port_type(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[smtp]\nhost = "smtp.example.com"\nport = "not-an-int"\n\n'
        '[notification]\nfrom = "nuself@localhost"\nto = "user@example.com"\n',
        encoding="utf-8",
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
    assert adapter._config is None
