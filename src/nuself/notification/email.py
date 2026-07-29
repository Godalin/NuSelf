"""Email notification adapter using SMTP."""

from __future__ import annotations

import smtplib
from collections.abc import Mapping
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import cast

from nuself.notification import OutboxEntry
from nuself.notification.deep_link import DeepLink
from nuself.notification.audit import (
    report_notification_failure,
    run_notification_observed,
    write_notification_audit,
)

EmailConfig = dict[str, str | int | bool]


class EmailConfigError(ValueError):
    """Declared private email configuration failure."""


class EmailNotificationAdapter:
    """Deliver outbox entries as emails via SMTP.

    Configuration is read from ``private/email.toml`` under the project root.
    The file is ignored by Git and must be created manually.

    Example ``private/email.toml``::

        [smtp]
        host = "smtp.gmail.com"
        port = 587
        user = "user@gmail.com"
        password = "app-password"

        [notification]
        from = "nuself@localhost"
        to = "user@example.com"
    """

    delivery_id = "email"

    def __init__(self, project_root: Path | None = None, *, dry_run: bool = False) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._dry_run = dry_run
        self._config = self._load_config()

    def send(self, entry: OutboxEntry) -> bool:
        if self._dry_run:
            write_notification_audit(
                "email_dry_run",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return True

        if not self._config:
            report_notification_failure(
                RuntimeError("email configuration is not available"),
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
            host = str(self._config["host"])
            port = int(self._config["port"])
            with smtplib.SMTP(host, port, timeout=30) as server:
                if bool(self._config.get("use_tls", True)):
                    server.starttls()
                user = self._config.get("user")
                password = self._config.get("password")
                if isinstance(user, str) and isinstance(password, str):
                    server.login(user, password)
                server.send_message(msg)
        except (OSError, ValueError, smtplib.SMTPException) as exc:
            report_notification_failure(
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

    def _load_config(self) -> EmailConfig | None:
        config_path = self._project_root / "private" / "email.toml"
        if not config_path.exists():
            return None

        return run_notification_observed(
            lambda: _decode_email_config(config_path),
            event="email_config_invalid",
            project_root=self._project_root,
            metadata={"record": config_path.name},
            errors=(EmailConfigError,),
        )


def _decode_email_config(config_path: Path) -> EmailConfig:
    """Decode one present email config without exposing values in errors."""

    import tomllib

    try:
        with config_path.open("rb") as file:
            data: dict[str, object] = tomllib.load(file)
    except OSError:
        raise EmailConfigError(
            "email configuration could not be read"
        ) from None
    except tomllib.TOMLDecodeError:
        raise EmailConfigError(
            "email configuration TOML is malformed"
        ) from None

    smtp = _require_table(data, "smtp")
    notification = _require_table(data, "notification")

    config: EmailConfig = {
        "host": _require_nonempty_string(smtp, "host", section="smtp"),
        "from": _require_header_string(
            notification,
            "from",
            section="notification",
        ),
        "to": _require_header_string(
            notification,
            "to",
            section="notification",
        ),
    }

    port = smtp.get("port")
    if type(port) is not int or not 1 <= port <= 65_535:
        raise EmailConfigError(
            "email configuration smtp.port must be an integer from 1 to 65535"
        )
    config["port"] = port

    use_tls = smtp.get("use_tls")
    if use_tls is not None:
        if not isinstance(use_tls, bool):
            raise EmailConfigError(
                "email configuration smtp.use_tls must be a boolean"
            )
        config["use_tls"] = use_tls

    user = smtp.get("user")
    password = smtp.get("password")
    if (user is None) != (password is None):
        raise EmailConfigError(
            "email configuration smtp.user and smtp.password must be provided together"
        )
    if user is not None and password is not None:
        if not isinstance(user, str) or not user.strip():
            raise EmailConfigError(
                "email configuration smtp.user must be a non-empty string"
            )
        if not isinstance(password, str) or not password.strip():
            raise EmailConfigError(
                "email configuration smtp.password must be a non-empty string"
            )
        config["user"] = user
        config["password"] = password

    return config


def _require_table(
    data: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise EmailConfigError(
            f"email configuration [{key}] must be a table"
        )
    return cast(dict[str, object], value)


def _require_nonempty_string(
    data: Mapping[str, object],
    key: str,
    *,
    section: str,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EmailConfigError(
            f"email configuration {section}.{key} must be a non-empty string"
        )
    return value


def _require_header_string(
    data: Mapping[str, object],
    key: str,
    *,
    section: str,
) -> str:
    value = _require_nonempty_string(data, key, section=section)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EmailConfigError(
            f"email configuration {section}.{key} contains control characters"
        )
    return value


def _build_email_message(
    entry: OutboxEntry,
    config: EmailConfig,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = entry.title
    msg["From"] = config["from"]
    msg["To"] = config["to"]
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
