"""Typed, sealed handler registration and dispatch."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from threading import RLock
from typing import Generic, ParamSpec, Protocol, TypeVar

HandlerKey = TypeVar("HandlerKey", bound=Hashable)
HandlerParams = ParamSpec("HandlerParams")
HandlerResult = TypeVar("HandlerResult")
MiddlewareKey = TypeVar(
    "MiddlewareKey",
    bound=Hashable,
    contravariant=True,
)
MiddlewareResult = TypeVar("MiddlewareResult")


class HandlerMiddleware(
    Protocol[MiddlewareKey, HandlerParams, MiddlewareResult]
):
    """One typed synchronous wrapper around the next request handler."""

    def __call__(
        self,
        key: MiddlewareKey,
        next_handler: Callable[HandlerParams, MiddlewareResult],
        *args: HandlerParams.args,
        **kwargs: HandlerParams.kwargs,
    ) -> MiddlewareResult: ...


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

    def __init__(
        self,
        middleware: Iterable[
            HandlerMiddleware[HandlerKey, HandlerParams, HandlerResult]
        ] = (),
    ) -> None:
        self._handlers: dict[
            HandlerKey,
            Callable[HandlerParams, HandlerResult],
        ] = {}
        self._middleware = list(middleware)
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

    def use(
        self,
        middleware: HandlerMiddleware[
            HandlerKey,
            HandlerParams,
            HandlerResult,
        ],
    ) -> None:
        """Append middleware while the registry is still being composed."""

        with self._lock:
            if self._sealed:
                raise HandlerRegistrySealedError(
                    "handler registry is sealed; cannot add middleware"
                )
            self._middleware.append(middleware)

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
        handler = self.resolve(key)
        with self._lock:
            middleware = tuple(self._middleware)
        for wrapper in reversed(middleware):
            handler = _wrap_handler(key, wrapper, handler)
        return handler(*args, **kwargs)


def _wrap_handler(
    key: HandlerKey,
    middleware: HandlerMiddleware[
        HandlerKey,
        HandlerParams,
        HandlerResult,
    ],
    next_handler: Callable[HandlerParams, HandlerResult],
) -> Callable[HandlerParams, HandlerResult]:
    def wrapped(
        *args: HandlerParams.args,
        **kwargs: HandlerParams.kwargs,
    ) -> HandlerResult:
        return middleware(key, next_handler, *args, **kwargs)

    return wrapped
