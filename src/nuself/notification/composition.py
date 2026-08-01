"""Canonical notification-adapter composition root."""

from __future__ import annotations

from nuself.config import RuntimePaths, SystemConfig
from nuself.notification.adapters import (
    LogOnlyNotificationAdapter,
    NotificationAdapter,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter


def build_notification_adapters(
    paths: RuntimePaths,
    *,
    config: SystemConfig,
) -> tuple[NotificationAdapter, ...]:
    """Build one ordered adapter plan shared by every runtime surface."""

    adapters: list[NotificationAdapter] = []
    if config.email.enabled:
        adapters.append(
            EmailNotificationAdapter(
                paths.project_root,
                config=config.email,
            )
        )
    if config.macos_notification.enabled:
        adapters.append(MacOSNotificationAdapter(paths.project_root))
    if not adapters:
        adapters.append(LogOnlyNotificationAdapter(paths))
    return tuple(adapters)
