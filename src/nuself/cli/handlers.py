"""Typed argparse handler binding and dispatch boundary."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import cast

from nuself.cli.exit_codes import CliExitCode
from nuself.runtime.handlers import HandlerRegistry
from nuself.cli.readiness import (
    CommandRequirements,
    INITIALIZED_AUTHORITY,
    NO_READINESS,
    inspect_command_readiness,
)
from nuself.config.scope import NuSelfScope

type CliHandler = Callable[[argparse.Namespace], int]
type CliHandlerRegistry = HandlerRegistry[
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
        *,
        requirements: CommandRequirements = INITIALIZED_AUTHORITY,
    ) -> None:
        """Register one stable parser key and bind only that key."""

        key = parser.prog
        self._registry.register(key, handler)
        parser.set_defaults(
            handler_key=key,
            help_parser=None,
            command_requirements=requirements,
        )

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
        return CliExitCode.SUCCESS
    if not isinstance(handler_key, str) or not handler_key:
        raise TypeError("CLI handler key is invalid")
    raw_registry = getattr(root_parser, _REGISTRY_ATTRIBUTE, None)
    if not isinstance(raw_registry, HandlerRegistry):
        raise TypeError("CLI handler registry is missing")
    registry = cast(CliHandlerRegistry, raw_registry)
    requirements = getattr(args, "command_requirements", None)
    if not isinstance(requirements, CommandRequirements):
        raise TypeError("CLI command readiness requirements are missing")
    if requirements != NO_READINESS:
        scope = getattr(args, "scope", None)
        if not isinstance(scope, NuSelfScope):
            raise TypeError("CLI scope was not resolved before readiness")
        readiness_failure = inspect_command_readiness(
            scope,
            requirements,
            message=getattr(args, "message", None),
        )
        if readiness_failure is not None:
            print(readiness_failure.render(), file=sys.stderr)
            return readiness_failure.exit_code
    result = cast(object, registry.dispatch(handler_key, args))
    if isinstance(result, bool) or not isinstance(result, int):
        raise TypeError("CLI handler must return an integer exit status")
    return result
