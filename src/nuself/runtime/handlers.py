"""Typed, sealed handler registration and dispatch."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from threading import RLock
from typing import Generic, ParamSpec, TypeVar

HandlerKey = TypeVar("HandlerKey", bound=Hashable)
HandlerParams = ParamSpec("HandlerParams")
HandlerResult = TypeVar("HandlerResult")


class HandlerRegistryError(RuntimeError):
    """Base class for handler registry composition errors."""


class DuplicateHandlerError(HandlerRegistryError):
    """Raised when the same handler key is registered twice."""


class HandlerRegistrySealedError(HandlerRegistryError):
    """Raised when registration is attempted after composition."""


class UnknownHandlerError(HandlerRegistryError):
    """Raised when dispatch targets an unregistered key."""


class HandlerRegistry(
    Generic[HandlerKey, HandlerParams, HandlerResult]
):
    """Maps one key to one callable and seals after composition."""

    def __init__(self) -> None:
        self._handlers: dict[
            HandlerKey,
            Callable[HandlerParams, HandlerResult],
        ] = {}
        self._sealed = False
        self._lock = RLock()

    @property
    def sealed(self) -> bool:
        with self._lock:
            return self._sealed

    @property
    def registered_keys(self) -> tuple[HandlerKey, ...]:
        with self._lock:
            return tuple(self._handlers)

    def register(
        self,
        key: HandlerKey,
        handler: Callable[HandlerParams, HandlerResult],
    ) -> None:
        with self._lock:
            if self._sealed:
                raise HandlerRegistrySealedError(
                    f"handler registry is sealed; cannot register {key!r}"
                )
            if key in self._handlers:
                raise DuplicateHandlerError(
                    f"handler already registered for {key!r}"
                )
            self._handlers[key] = handler

    def handler(
        self,
        key: HandlerKey,
    ) -> Callable[
        [Callable[HandlerParams, HandlerResult]],
        Callable[HandlerParams, HandlerResult],
    ]:
        """Return a registration decorator for composition code."""

        def register_handler(
            handler: Callable[HandlerParams, HandlerResult],
        ) -> Callable[HandlerParams, HandlerResult]:
            self.register(key, handler)
            return handler

        return register_handler

    def seal(self) -> HandlerRegistry[
        HandlerKey,
        HandlerParams,
        HandlerResult,
    ]:
        with self._lock:
            self._sealed = True
        return self

    def resolve(
        self,
        key: HandlerKey,
    ) -> Callable[HandlerParams, HandlerResult]:
        with self._lock:
            try:
                return self._handlers[key]
            except KeyError as exc:
                raise UnknownHandlerError(
                    f"no handler registered for {key!r}"
                ) from exc

    def dispatch(
        self,
        key: HandlerKey,
        *args: HandlerParams.args,
        **kwargs: HandlerParams.kwargs,
    ) -> HandlerResult:
        return self.resolve(key)(*args, **kwargs)
