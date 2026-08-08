"""Bounded turn-scoped live activity broker for daemon clients."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Condition
from uuid import uuid4

from nuself.log.record import LogEvent


class ActivitySubscriptionNotFound(LookupError):
    """Raised when a subscription is unknown or expired."""


@dataclass(frozen=True)
class ActivityBatch:
    """One bounded activity read plus loss since the previous read."""

    events: tuple[LogEvent, ...]
    dropped_count: int


@dataclass
class _ActivitySubscription:
    turn_id: str
    events: deque[LogEvent] = field(default_factory=lambda: deque[LogEvent]())
    recent_event_ids: deque[str] = field(default_factory=lambda: deque[str]())
    recent_event_id_set: set[str] = field(default_factory=lambda: set[str]())
    dropped_count: int = 0
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
                event_id = event.event_id
                if (
                    event_id is not None
                    and event_id in subscription.recent_event_id_set
                ):
                    continue
                subscription.events.append(event)
                if event_id is not None:
                    subscription.recent_event_ids.append(event_id)
                    subscription.recent_event_id_set.add(event_id)
                    while len(subscription.recent_event_ids) > self._max_events:
                        expired_event_id = subscription.recent_event_ids.popleft()
                        subscription.recent_event_id_set.remove(expired_event_id)
                while len(subscription.events) > self._max_events:
                    subscription.events.popleft()
                    subscription.dropped_count += 1
                delivered = True
            if delivered:
                self._condition.notify_all()

    def next_events(
        self,
        subscription_id: str,
        *,
        timeout_seconds: float,
        limit: int,
    ) -> ActivityBatch:
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
                    events = tuple(
                        subscription.events.popleft()
                        for _ in range(count)
                    )
                    dropped_count = subscription.dropped_count
                    subscription.dropped_count = 0
                    return ActivityBatch(events, dropped_count)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ActivityBatch((), 0)
                self._condition.wait(remaining)

    def close(self, subscription_id: str) -> None:
        with self._condition:
            self._subscriptions.pop(subscription_id, None)

    def _expire_locked(self) -> None:
        cutoff = time.monotonic() - self._ttl_seconds
        expired = [
            subscription_id
            for subscription_id, subscription in self._subscriptions.items()
            if subscription.last_access_at < cutoff
        ]
        for subscription_id in expired:
            self._subscriptions.pop(subscription_id, None)
