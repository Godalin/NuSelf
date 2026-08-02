"""Canonical notification-adapter composition root."""

from __future__ import annotations

from nuself.config.settings import EmailConfig, MacosNotificationConfig, RuntimePaths
from nuself.notification.adapters import (
    LogOnlyNotificationAdapter,
    NotificationAdapter,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter


def build_notification_adapters(
    paths: RuntimePaths,
    *,
    email_config: EmailConfig,
    macos_config: MacosNotificationConfig,
) -> tuple[NotificationAdapter, ...]:
    """Build one ordered adapter plan shared by every runtime surface."""

    adapters: list[NotificationAdapter] = []
    if email_config.enabled:
        adapters.append(
            EmailNotificationAdapter(
                paths.authority_root,
                config=email_config,
            )
        )
    if macos_config.enabled:
        adapters.append(MacOSNotificationAdapter(paths.authority_root))
    if not adapters:
        adapters.append(LogOnlyNotificationAdapter(paths.authority_root))
    return tuple(adapters)
