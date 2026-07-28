"""Bounded turn-scoped live activity broker for daemon clients."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Condition
from uuid import uuid4

from nuself.logs import LogEvent


class ActivitySubscriptionNotFound(LookupError):
    """Raised when a subscription is unknown or expired."""


@dataclass
class _ActivitySubscription:
    turn_id: str
    events: deque[LogEvent] = field(default_factory=lambda: deque[LogEvent]())
    last_access_at: float = field(default_factory=time.monotonic)


class ActivityBroker:
    """Fan out bounded live activity without using logs as a command bus."""

    def __init__(
        self,
        *,
        max_events_per_subscription: int = 256,
        subscription_ttl_seconds: float = 300.0,
    ) -> None:
        if max_events_per_subscription < 1:
            raise ValueError("activity queue bound must be positive")
        if subscription_ttl_seconds <= 0:
            raise ValueError("activity subscription TTL must be positive")
        self._max_events = max_events_per_subscription
        self._ttl_seconds = subscription_ttl_seconds
        self._condition = Condition()
        self._subscriptions: dict[str, _ActivitySubscription] = {}

    def open(self, turn_id: str) -> str:
        if not turn_id:
            raise ValueError("activity turn_id must not be empty")
        subscription_id = uuid4().hex
        with self._condition:
            self._expire_locked()
            self._subscriptions[subscription_id] = _ActivitySubscription(
                turn_id=turn_id
            )
        return subscription_id

    def publish(self, event: LogEvent) -> None:
        if event.turn_id is None:
            return
        with self._condition:
            self._expire_locked()
            delivered = False
            for subscription in self._subscriptions.values():
                if subscription.turn_id != event.turn_id:
                    continue
                subscription.events.append(event)
                while len(subscription.events) > self._max_events:
                    subscription.events.popleft()
                delivered = True
            if delivered:
                self._condition.notify_all()

    def next_events(
        self,
        subscription_id: str,
        *,
        timeout_seconds: float,
        limit: int,
    ) -> tuple[LogEvent, ...]:
        if timeout_seconds < 0:
            raise ValueError("activity timeout must not be negative")
        if limit < 1:
            raise ValueError("activity batch limit must be positive")
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                self._expire_locked()
                subscription = self._subscriptions.get(subscription_id)
                if subscription is None:
                    raise ActivitySubscriptionNotFound(subscription_id)
                subscription.last_access_at = time.monotonic()
                if subscription.events:
                    count = min(limit, len(subscription.events))
                    return tuple(subscription.events.popleft() for _ in range(count))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ()
                self._condition.wait(remaining)

    def close(self, subscription_id: str) -> bool:
        with self._condition:
            removed = self._subscriptions.pop(subscription_id, None)
            return removed is not None

    def _expire_locked(self) -> None:
        cutoff = time.monotonic() - self._ttl_seconds
        expired = [
            subscription_id
            for subscription_id, subscription in self._subscriptions.items()
            if subscription.last_access_at < cutoff
        ]
        for subscription_id in expired:
            self._subscriptions.pop(subscription_id, None)
