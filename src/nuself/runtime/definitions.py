"""Generic duplicate-safe definition registration and lookup."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from threading import RLock
from typing import Generic, TypeVar

DefinitionKey = TypeVar("DefinitionKey", bound=Hashable)
Definition = TypeVar("Definition")


class DuplicateDefinitionError(ValueError):
    """A registry already owns the requested definition key."""

    def __init__(self, namespace: str, key: object) -> None:
        super().__init__(
            f"{namespace} definition already registered: {key!r}"
        )
        self.namespace = namespace
        self.key = key


class DefinitionRegistrySealedError(RuntimeError):
    """A sealed definition registry rejected further mutation."""

    def __init__(self, namespace: str) -> None:
        super().__init__(f"{namespace} definition registry is sealed")
        self.namespace = namespace


class UnknownDefinitionError(LookupError):
    """A registry does not own the requested definition key."""

    def __init__(self, namespace: str, key: object) -> None:
        super().__init__(f"{namespace} definition is not registered: {key!r}")
        self.namespace = namespace
        self.key = key


class DefinitionRegistry(Generic[DefinitionKey, Definition]):
    """Ordered registry sealed explicitly after composition."""

    def __init__(
        self,
        key_of: Callable[[Definition], DefinitionKey],
        *,
        namespace: str,
    ) -> None:
        if not callable(key_of):
            raise TypeError("definition key function must be callable")
        if not namespace:
            raise ValueError("definition registry namespace must not be empty")
        self._key_of = key_of
        self._namespace = namespace
        self._definitions: dict[DefinitionKey, Definition] = {}
        self._sealed = False
        self._lock = RLock()

    def register(
        self,
        definition: Definition,
    ) -> DefinitionRegistry[DefinitionKey, Definition]:
        key = self._key_of(definition)
        with self._lock:
            if self._sealed:
                raise DefinitionRegistrySealedError(self._namespace)
            if key in self._definitions:
                raise DuplicateDefinitionError(self._namespace, key)
            self._definitions[key] = definition
        return self

    def resolve(self, key: DefinitionKey) -> Definition:
        with self._lock:
            try:
                return self._definitions[key]
            except KeyError as exc:
                raise UnknownDefinitionError(
                    self._namespace,
                    key,
                ) from exc

    def seal(self) -> DefinitionRegistry[DefinitionKey, Definition]:
        with self._lock:
            self._sealed = True
        return self

    @property
    def definitions(self) -> tuple[Definition, ...]:
        with self._lock:
            return tuple(self._definitions.values())

    @property
    def is_sealed(self) -> bool:
        with self._lock:
            return self._sealed
