"""Tests for the unified-config email adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nuself.config.settings import EmailConfig, EmailSmtpConfig
from nuself.log.reader import read_log_events
from nuself.notification.model import OutboxEntry
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


def _email_config(*, authenticated: bool = True) -> EmailConfig:
    return EmailConfig(
        enabled=True,
        smtp=EmailSmtpConfig(
            host="smtp.example.com",
            port=587,
            username="user" if authenticated else "",
            password="secret" if authenticated else "",
        ),
        from_address="nuself@example.com",
        to_address="owner@example.com",
    )


def test_dry_run_returns_true_and_logs(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=EmailConfig(),
        dry_run=True,
    )

    assert adapter.send(entry) is True
    [event] = read_log_events(
        project_root=tmp_path,
        component="outbox",
    )
    assert event.event == "email_dry_run"
    assert event.status == "simulated"
    assert event.metadata == {"entry_id": "test-001", "attempt": 0}
    assert "Test Title" not in event.message
    assert "Test body." not in event.message


def test_disabled_email_returns_false(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=EmailConfig(),
    )

    assert adapter.send(entry) is False
    assert read_log_events(
        project_root=tmp_path,
        component="outbox",
    )[-1].event == "email_no_config"


def test_send_uses_unified_smtp_config(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(),
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        server = MagicMock()
        server.__enter__.return_value = server
        smtp.return_value = server

        assert adapter.send(entry) is True

    smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("user", "secret")
    message = server.send_message.call_args.args[0]
    assert message["From"] == "nuself@example.com"
    assert message["To"] == "owner@example.com"


def test_send_without_authentication(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(authenticated=False),
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        server = MagicMock()
        server.__enter__.return_value = server
        smtp.return_value = server

        assert adapter.send(entry) is True

    server.login.assert_not_called()


def test_html_message_escapes_body_and_link(tmp_path: Path) -> None:
    entry = OutboxEntry(
        id="safe-html",
        title="Safe",
        body='<script>alert("x")</script> & text',
        status="pending",
        idempotency_key="safe-html",
        deep_link="nuself://new-conversation?title=A&message=B",
    )
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(),
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        server = MagicMock()
        server.__enter__.return_value = server
        smtp.return_value = server
        assert adapter.send(entry) is True

    message = server.send_message.call_args.args[0]
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    html_content = html_part.get_content()
    assert "<script>" not in html_content
    assert "&lt;script&gt;" in html_content
    assert "title=A&amp;message=B" in html_content


@pytest.mark.parametrize(
    "deep_link",
    [
        "https://example.com/phishing",
        "nuself://unknown/path",
        "nuself://new-thread#unexpected",
    ],
)
def test_invalid_deep_link_fails_before_smtp(
    tmp_path: Path,
    deep_link: str,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(),
    )
    entry = OutboxEntry(
        id="invalid-link",
        title="Invalid link",
        body="Body",
        status="pending",
        idempotency_key="invalid-link",
        deep_link=deep_link,
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        assert adapter.send(entry) is False
        smtp.assert_not_called()


def test_invalid_subject_fails_before_smtp(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    invalid = OutboxEntry(
        id=entry.id,
        title="Subject\nBcc: attacker@example.com",
        body=entry.body,
        status=entry.status,
        idempotency_key=entry.idempotency_key,
    )
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(),
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        assert adapter.send(invalid) is False
        smtp.assert_not_called()


def test_smtp_failure_is_redacted_and_returns_false(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    adapter = EmailNotificationAdapter(
        tmp_path,
        config=_email_config(),
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        smtp.side_effect = OSError("network error")
        assert adapter.send(entry) is False

    event = read_log_events(
        project_root=tmp_path,
        component="outbox",
    )[-1]
    assert event.event == "email_failed"
    assert "secret" not in (event.error or "")
