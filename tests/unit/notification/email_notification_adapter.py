"""Tests for EmailNotificationAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nuself.logs import read_log_events
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
    [event] = read_log_events(
        project_root=tmp_path,
        component="outbox",
    )
    assert event.event == "email_dry_run"
    assert event.status == "simulated"
    assert event.metadata == {"entry_id": "test-001", "attempt": 0}
    assert "Test Title" not in event.message
    assert "Test body." not in event.message
    assert "key-001" not in str(event.metadata)


def test_no_config_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
    assert read_log_events(project_root=tmp_path, component="outbox") == []
    assert adapter.send(entry) is False


def test_no_config_diagnostic_failure_preserves_false(
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
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = adapter.send(entry)

    assert result is False


def test_send_with_config(tmp_path: Path, entry: OutboxEntry) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()

        def _enter(_self: object) -> object:
            return _self

        def _exit(_self: object, *_args: object) -> None:
            return None

        mock_server.__enter__ = _enter
        mock_server.__exit__ = _exit
        mock_smtp_cls.return_value = mock_server
        assert adapter.send(entry) is True
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("u", "p")
        mock_server.send_message.assert_called_once()


def test_html_message_escapes_body_and_canonical_deep_link(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    entry = OutboxEntry(
        id="safe-html",
        title="Safe",
        body='<script>alert("x")</script> & text',
        status="pending",
        idempotency_key="safe-html",
        deep_link="nuself://new-thread?title=A&message=B",
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

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
    assert (
        'href="nuself://new-thread?title=A&message=B"'
        not in html_content
    )
    assert (
        'href="nuself://new-thread?title=A&message=B"'.replace(
            "&", "&amp;"
        )
        in html_content
    )


@pytest.mark.parametrize(
    "deep_link",
    [
        "https://example.com/phishing",
        "nuself://unknown/path",
        "nuself://new-thread#unexpected",
    ],
)
def test_invalid_deep_link_returns_false_before_smtp(
    tmp_path: Path,
    deep_link: str,
) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
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

    assert read_log_events(
        project_root=tmp_path,
        component="outbox",
    )[-1].event == "email_failed"


def test_invalid_subject_header_returns_false_before_smtp(
    tmp_path: Path,
    entry: OutboxEntry,
) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
    invalid = OutboxEntry(
        id=entry.id,
        title="Subject\nBcc: attacker@example.com",
        body=entry.body,
        status=entry.status,
        idempotency_key=entry.idempotency_key,
    )

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        assert adapter.send(invalid) is False
        smtp.assert_not_called()


def test_send_failure_returns_false(tmp_path: Path, entry: OutboxEntry) -> None:
    _write_config(tmp_path)
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("network error")
        assert adapter.send(entry) is False


def test_smtp_diagnostic_failure_preserves_false(
    tmp_path: Path,
    entry: OutboxEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(tmp_path)

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)

    with patch("nuself.notification.email.smtplib.SMTP") as smtp:
        smtp.side_effect = OSError("network error")
        with pytest.warns(
            RuntimeWarning,
            match="runtime/observability_sink_failed",
        ):
            result = adapter.send(entry)

    assert result is False


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


def test_load_config_ignores_invalid_port_type(tmp_path: Path, entry: OutboxEntry) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[smtp]\nhost = "smtp.example.com"\nport = "not-an-int"\n\n'
        '[notification]\nfrom = "nuself@localhost"\nto = "user@example.com"\n',
        encoding="utf-8",
    )
    adapter = EmailNotificationAdapter(tmp_path, dry_run=False)
    event = read_log_events(project_root=tmp_path, component="outbox")[-1]
    assert event.event == "email_config_invalid"
    assert event.status == "degraded"
    assert event.metadata == {"record": "email.toml"}
    assert adapter.send(entry) is False


@pytest.mark.parametrize(
    "content",
    [
        'secret = "do-not-log"\nthis is not toml',
        (
            'smtp = "not-a-table"\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = ""\nport = 25\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = "smtp.example.com"\nport = true\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = "smtp.example.com"\nport = 65536\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = "smtp.example.com"\nport = 25\n'
            'use_tls = "yes"\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = "smtp.example.com"\nport = 25\n'
            'user = "user"\n'
            '[notification]\nfrom = "from@example.com"\n'
            'to = "to@example.com"\n'
        ),
        (
            '[smtp]\nhost = "smtp.example.com"\nport = 25\n'
            '[notification]\nfrom = "from@example.com\\nBcc: attacker@example.com"\n'
            'to = "to@example.com"\n'
        ),
    ],
)
def test_present_invalid_config_is_observable_without_values(
    tmp_path: Path,
    content: str,
) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(content, encoding="utf-8")

    adapter = EmailNotificationAdapter(tmp_path)

    assert adapter._config is None  # pyright: ignore[reportPrivateUsage]
    events = read_log_events(project_root=tmp_path, component="outbox")
    assert len(events) == 1
    assert events[0].event == "email_config_invalid"
    assert events[0].metadata == {"record": "email.toml"}
    assert "do-not-log" not in (events[0].error or "")


def test_present_unreadable_config_is_observable(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.mkdir(parents=True)

    adapter = EmailNotificationAdapter(tmp_path)

    assert adapter._config is None  # pyright: ignore[reportPrivateUsage]
    event = read_log_events(project_root=tmp_path, component="outbox")[-1]
    assert event.event == "email_config_invalid"
    assert event.error == "email configuration could not be read"


def test_undeclared_config_decoder_failure_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "private" / "email.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("", encoding="utf-8")

    def fail(config_path: Path) -> dict[str, object]:
        raise TypeError("decoder invariant broken")

    monkeypatch.setattr(
        "nuself.notification.email._decode_email_config",
        fail,
    )

    with pytest.raises(TypeError, match="decoder invariant broken"):
        EmailNotificationAdapter(tmp_path)
