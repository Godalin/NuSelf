from __future__ import annotations

from collections.abc import Callable

import pytest

from nuself.runtime.handlers import (
    DuplicateHandlerError,
    HandlerRegistry,
    HandlerRegistrySealedError,
    HandlerRegistryUnsealedError,
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
    registry.seal()
    assert registry.dispatch("echo", "hello") == "hello"


def test_handler_registry_rejects_raw_resolution_after_seal() -> None:
    calls: list[str] = []
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()

    def observe(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        calls.append(key)
        return next_handler(value)

    registry.use(observe)
    registry.register("echo", lambda value: value)
    registry.seal()

    with pytest.raises(
        HandlerRegistrySealedError,
        match="raw handlers are unavailable",
    ):
        registry.resolve("echo")

    assert registry.dispatch("echo", "safe") == "safe"
    assert calls == ["echo"]


def test_handler_registry_rejects_dispatch_before_seal() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    registry.register("echo", lambda value: value)

    with pytest.raises(HandlerRegistryUnsealedError):
        registry.dispatch("echo", "hello")


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


def test_handler_middleware_wraps_in_registration_order() -> None:
    calls: list[str] = []
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()

    def outer(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        calls.append(f"outer-before:{key}")
        result = next_handler(value)
        calls.append("outer-after")
        return result

    def inner(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        calls.append(f"inner-before:{key}")
        result = next_handler(value)
        calls.append("inner-after")
        return result

    registry.use(outer)
    registry.use(inner)
    registry.register(
        "echo",
        lambda value: calls.append("handler") or value,
    )
    registry.seal()

    assert registry.dispatch("echo", "hello") == "hello"
    assert calls == [
        "outer-before:echo",
        "inner-before:echo",
        "handler",
        "inner-after",
        "outer-after",
    ]


def test_handler_registry_compiles_middleware_only_when_sealed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.runtime import handlers

    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()

    def passthrough(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        del key
        return next_handler(value)

    registry.use(passthrough)
    registry.register("echo", lambda value: value)
    registry.seal()

    def reject_runtime_compilation(*args: object) -> object:
        del args
        raise AssertionError("middleware chain rebuilt during dispatch")

    monkeypatch.setattr(handlers, "_wrap_handler", reject_runtime_compilation)

    assert registry.dispatch("echo", "stable") == "stable"


def test_handler_middleware_preserves_handler_exception() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    observed: list[BaseException] = []

    def observe(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        del key
        try:
            return next_handler(value)
        except BaseException as exc:
            observed.append(exc)
            raise

    failure = RuntimeError("handler failed")

    def fail(value: str) -> str:
        del value
        raise failure

    registry.use(observe)
    registry.register("fail", fail)
    registry.seal()

    with pytest.raises(RuntimeError) as captured:
        registry.dispatch("fail", "value")

    assert captured.value is failure
    assert observed == [failure]


def test_handler_registry_rejects_middleware_after_seal() -> None:
    registry: HandlerRegistry[str, [str], str] = HandlerRegistry()
    registry.seal()

    def passthrough(
        key: str,
        next_handler: Callable[[str], str],
        value: str,
    ) -> str:
        del key
        return next_handler(value)

    with pytest.raises(HandlerRegistrySealedError):
        registry.use(passthrough)
