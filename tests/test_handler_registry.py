from __future__ import annotations

import pytest

from nuself.runtime.handlers import (
    DuplicateHandlerError,
    HandlerRegistry,
    HandlerRegistrySealedError,
    UnknownHandlerError,
)


def test_handler_registry_dispatches_registered_handler() -> None:
    registry: HandlerRegistry[str, [int, int], int] = (
        HandlerRegistry()
    )
    registry.register("add", lambda left, right: left + right)
    registry.seal()

    assert registry.dispatch("add", 2, 3) == 5
    assert registry.registered_keys == ("add",)
    assert registry.sealed


def test_handler_registry_decorator_returns_original_handler() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()

    @registry.handler("echo")
    def echo(value: str) -> str:
        return value

    assert registry.resolve("echo") is echo
    assert registry.dispatch("echo", "hello") == "hello"


def test_handler_registry_rejects_duplicate_registration() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    registry.register("echo", lambda value: value)

    with pytest.raises(DuplicateHandlerError):
        registry.register("echo", lambda value: value)


def test_handler_registry_rejects_registration_after_seal() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    registry.seal()

    with pytest.raises(HandlerRegistrySealedError):
        registry.register("echo", lambda value: value)


def test_handler_registry_rejects_unknown_dispatch() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    registry.seal()

    with pytest.raises(UnknownHandlerError):
        registry.dispatch("missing", "value")
