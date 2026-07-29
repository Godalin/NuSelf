"""Typed, sealed handler registration and dispatch."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from threading import RLock
from types import MappingProxyType
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


class HandlerRegistryUnsealedError(HandlerRegistryError):
    """Raised when runtime dispatch starts before composition is sealed."""


class HandlerRegistryCoverageError(HandlerRegistryError):
    """Raised when a closed catalog and its registered handlers differ."""

    def __init__(
        self,
        *,
        missing: frozenset[Hashable],
        extra: frozenset[Hashable],
    ) -> None:
        self.missing = missing
        self.extra = extra
        super().__init__(
            "handler registry coverage differs "
            f"(missing={_ordered_key_reprs(missing)!r}, "
            f"extra={_ordered_key_reprs(extra)!r})"
        )


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
        for wrapper in self._middleware:
            _require_callable(wrapper, role="handler middleware")
        self._sealed = False
        self._dispatch_handlers: MappingProxyType[
            HandlerKey,
            Callable[HandlerParams, HandlerResult],
        ] | None = None
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
            _require_callable(handler, role="handler")
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
            _require_callable(middleware, role="handler middleware")
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

    def seal(
        self,
        *,
        expected_keys: Iterable[HandlerKey] | None = None,
    ) -> HandlerRegistry[
        HandlerKey,
        HandlerParams,
        HandlerResult,
    ]:
        """Seal after optionally proving exact closed-catalog coverage."""

        with self._lock:
            if expected_keys is not None:
                expected = frozenset(expected_keys)
                actual = frozenset(self._handlers)
                missing = expected - actual
                extra = actual - expected
                if missing or extra:
                    raise HandlerRegistryCoverageError(
                        missing=frozenset(missing),
                        extra=frozenset(extra),
                    )
            if self._sealed:
                return self
            dispatch_handlers: dict[
                HandlerKey,
                Callable[HandlerParams, HandlerResult],
            ] = {}
            for key, registered_handler in self._handlers.items():
                handler = registered_handler
                for wrapper in reversed(self._middleware):
                    handler = _wrap_handler(key, wrapper, handler)
                dispatch_handlers[key] = handler
            self._dispatch_handlers = MappingProxyType(dispatch_handlers)
            self._sealed = True
        return self

    def resolve(
        self,
        key: HandlerKey,
    ) -> Callable[HandlerParams, HandlerResult]:
        with self._lock:
            if self._sealed:
                raise HandlerRegistrySealedError(
                    "handler registry is sealed; raw handlers are unavailable"
                )
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
        with self._lock:
            dispatch_handlers = self._dispatch_handlers
            if dispatch_handlers is None:
                raise HandlerRegistryUnsealedError(
                    "handler registry must be sealed before dispatch"
                )
            try:
                handler = dispatch_handlers[key]
            except KeyError as exc:
                raise UnknownHandlerError(
                    f"no handler registered for {key!r}"
                ) from exc
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


def _require_callable(value: object, *, role: str) -> None:
    if not callable(value):
        raise TypeError(f"{role} must be callable")


def _ordered_key_reprs(keys: Iterable[Hashable]) -> list[str]:
    return sorted(repr(key) for key in keys)
