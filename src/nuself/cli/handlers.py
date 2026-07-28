"""Typed argparse handler binding and dispatch boundary."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import cast

CliHandler = Callable[[argparse.Namespace], int]


def bind_handler(
    parser: argparse.ArgumentParser,
    handler: CliHandler,
) -> None:
    """Bind one typed command handler to an argparse parser."""
    parser.set_defaults(handler=handler, help_parser=None)


def bind_help(parser: argparse.ArgumentParser) -> None:
    """Mark a command group as help-only until a child is selected."""
    parser.set_defaults(handler=None, help_parser=parser)


def dispatch_cli(
    args: argparse.Namespace,
    root_parser: argparse.ArgumentParser,
) -> int:
    """Dispatch parsed arguments through the CLI handler contract."""
    raw_handler = getattr(args, "handler", None)
    if raw_handler is None:
        help_parser = getattr(args, "help_parser", root_parser)
        if not isinstance(help_parser, argparse.ArgumentParser):
            raise TypeError("CLI help parser is invalid")
        help_parser.print_help()
        return 0
    if not callable(raw_handler):
        raise TypeError("CLI handler is not callable")
    handler = cast(Callable[[argparse.Namespace], object], raw_handler)
    result = handler(args)
    if isinstance(result, bool) or not isinstance(result, int):
        raise TypeError("CLI handler must return an integer exit status")
    return result
