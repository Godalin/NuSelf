"""Canonical notification-adapter composition root."""

from __future__ import annotations

from nuself.config import ConfigSystem, RuntimePaths, SystemConfig
from nuself.notification.adapters import (
    LogOnlyNotificationAdapter,
    NotificationAdapter,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter


def build_notification_adapters(
    paths: RuntimePaths,
    *,
    config: SystemConfig | None = None,
) -> list[NotificationAdapter]:
    """Build one ordered adapter plan shared by every runtime surface."""

    effective = (
        config
        if config is not None
        else ConfigSystem.load(project_root=paths.project_root)
    )
    adapters: list[NotificationAdapter] = []
    if effective.email.enabled:
        adapters.append(
            EmailNotificationAdapter(
                paths.project_root,
                config=effective.email,
            )
        )
    if effective.macos_notification.enabled:
        adapters.append(MacOSNotificationAdapter(paths.project_root))
    if not adapters:
        adapters.append(LogOnlyNotificationAdapter(paths))
    return adapters
