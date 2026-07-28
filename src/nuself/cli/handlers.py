"""Typed argparse handler binding and dispatch boundary."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import cast

from nuself.runtime.handlers import HandlerRegistry

CliHandler = Callable[[argparse.Namespace], int]
CliHandlerRegistry = HandlerRegistry[
    str,
    [argparse.Namespace],
    int,
]
_REGISTRY_ATTRIBUTE = "_nuself_cli_handler_registry"


class CliHandlerBindings:
    """Compose one parser tree and its sealed handler registry."""

    def __init__(self) -> None:
        self._registry: CliHandlerRegistry = HandlerRegistry()

    def bind(
        self,
        parser: argparse.ArgumentParser,
        handler: CliHandler,
    ) -> None:
        """Register one stable parser key and bind only that key."""

        key = parser.prog
        self._registry.register(key, handler)
        parser.set_defaults(handler_key=key, help_parser=None)

    def bind_help(self, parser: argparse.ArgumentParser) -> None:
        """Mark a command group as help-only until a child is selected."""

        parser.set_defaults(handler_key=None, help_parser=parser)

    def seal(self, root_parser: argparse.ArgumentParser) -> None:
        """Seal and attach the complete registry to its root parser."""

        self._registry.seal()
        setattr(root_parser, _REGISTRY_ATTRIBUTE, self._registry)


def dispatch_cli(
    args: argparse.Namespace,
    root_parser: argparse.ArgumentParser,
) -> int:
    """Dispatch parsed arguments through the CLI handler contract."""
    handler_key = getattr(args, "handler_key", None)
    if handler_key is None:
        help_parser = getattr(args, "help_parser", root_parser)
        if not isinstance(help_parser, argparse.ArgumentParser):
            raise TypeError("CLI help parser is invalid")
        help_parser.print_help()
        return 0
    if not isinstance(handler_key, str) or not handler_key:
        raise TypeError("CLI handler key is invalid")
    raw_registry = getattr(root_parser, _REGISTRY_ATTRIBUTE, None)
    if not isinstance(raw_registry, HandlerRegistry):
        raise TypeError("CLI handler registry is missing")
    registry = cast(CliHandlerRegistry, raw_registry)
    result = cast(object, registry.dispatch(handler_key, args))
    if isinstance(result, bool) or not isinstance(result, int):
        raise TypeError("CLI handler must return an integer exit status")
    return result
