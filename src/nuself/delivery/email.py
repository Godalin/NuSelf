"""Email delivery adapter using unified system configuration."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from html import escape
from pathlib import Path

from nuself.config.settings import EmailConfig
from nuself.inbox.model import InboxItem
from nuself.delivery.audit import (
    DELIVERY_AUDIT,
)
from nuself.inbox.link import DeepLink


class EmailDeliveryAdapter:
    """Deliver Inbox items through configured SMTP."""

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

    def send(self, entry: InboxItem, *, attempt: int) -> bool:
        if self._dry_run:
            DELIVERY_AUDIT.write_strict(
                "email_dry_run",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
                },
            )
            return True

        if not self._config.enabled:
            DELIVERY_AUDIT.failure(
                RuntimeError("email notification is disabled"),
                event="email_no_config",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
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
            DELIVERY_AUDIT.failure(
                exc,
                event="email_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
                },
            )
            return False

        return True


def _build_email_message(
    entry: InboxItem,
    config: EmailConfig,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = entry.title
    msg["From"] = config.from_address
    msg["To"] = config.to_address
    msg.set_content(entry.body)
    if entry.deep_link is not None:
        canonical_link = DeepLink.parse(entry.deep_link).to_url()
        escaped_body = "<br>\n".join(
            escape(line) if line else "&nbsp;"
            for line in entry.body.splitlines()
        )
        escaped_link = escape(canonical_link, quote=True)
        msg.add_alternative(
            "<html><body>"
            f"<p>{escaped_body}</p>"
            f'<p><a href="{escaped_link}">Open</a></p>'
            "</body></html>",
            subtype="html",
        )
    return msg
