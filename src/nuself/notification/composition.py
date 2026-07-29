"""Canonical notification-adapter composition root."""

from __future__ import annotations

from pathlib import Path

from nuself.config import ConfigSystem, SystemConfig
from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationAdapter,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.notification.macos import MacOSNotificationAdapter


def build_notification_adapters(
    project_root: Path | None = None,
    *,
    config: SystemConfig | None = None,
) -> list[NotificationAdapter]:
    """Build one ordered adapter plan shared by every runtime surface."""

    effective = (
        config
        if config is not None
        else ConfigSystem.load(project_root=project_root)
    )
    adapters: list[NotificationAdapter] = []
    if effective.email.enabled:
        adapters.append(
            EmailNotificationAdapter(
                project_root,
                config=effective.email,
            )
        )
    if effective.macos_notification.enabled:
        adapters.append(MacOSNotificationAdapter(project_root))
    if not adapters:
        adapters.append(LogOnlyNotificationAdapter(project_root))
    return adapters
