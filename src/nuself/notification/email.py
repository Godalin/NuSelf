"""Email notification adapter using the unified system configuration."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from html import escape
from pathlib import Path

from nuself.config.settings import EmailConfig
from nuself.notification.model import OutboxEntry
from nuself.notification.audit import (
    NOTIFICATION_AUDIT,
)
from nuself.notification.deep_link import DeepLink


class EmailNotificationAdapter:
    """Deliver outbox entries through configured SMTP."""

    delivery_id = "email"

    def __init__(
        self,
        project_root: Path,
        *,
        config: EmailConfig,
        dry_run: bool = False,
    ) -> None:
        self._project_root = project_root
        self._dry_run = dry_run
        self._config = config

    def send(self, entry: OutboxEntry) -> bool:
        if self._dry_run:
            NOTIFICATION_AUDIT.write_strict(
                "email_dry_run",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return True

        if not self._config.enabled:
            NOTIFICATION_AUDIT.failure(
                RuntimeError("email notification is disabled"),
                event="email_no_config",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return False

        try:
            msg = _build_email_message(entry, self._config)
            smtp = self._config.smtp
            with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
                if smtp.use_tls:
                    server.starttls()
                if smtp.username and smtp.password:
                    server.login(smtp.username, smtp.password)
                server.send_message(msg)
        except (OSError, ValueError, smtplib.SMTPException) as exc:
            NOTIFICATION_AUDIT.failure(
                exc,
                event="email_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return False

        return True


def _build_email_message(
    entry: OutboxEntry,
    config: EmailConfig,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = entry.title
    msg["From"] = config.from_address
    msg["To"] = config.to_address
    msg.set_content(entry.body)
    if entry.deep_link is not None:
        canonical_link = DeepLink.parse(entry.deep_link).to_url()
        escaped_body = escape(entry.body)
        escaped_link = escape(canonical_link, quote=True)
        msg.add_alternative(
            "<html><body>"
            f"<p>{escaped_body}</p>"
            f'<p><a href="{escaped_link}">Open</a></p>'
            "</body></html>",
            subtype="html",
        )
    return msg
