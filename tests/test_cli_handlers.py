from __future__ import annotations

import argparse
from typing import cast

import pytest

from nuself.cli.handlers import CliHandler, bind_handler, bind_help, dispatch_cli


def test_bind_handler_dispatches_typed_exit_status() -> None:
    parser = argparse.ArgumentParser(prog="test")
    bind_handler(parser, lambda _args: 7)

    assert dispatch_cli(parser.parse_args([]), parser) == 7


def test_bind_help_prints_selected_parser_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = argparse.ArgumentParser(prog="test")
    subparsers = parser.add_subparsers(dest="command")
    group_parser = subparsers.add_parser("group")
    bind_help(group_parser)

    assert dispatch_cli(parser.parse_args(["group"]), parser) == 0
    assert capsys.readouterr().out.startswith("usage: test group")


def test_dispatch_rejects_non_callable_handler() -> None:
    parser = argparse.ArgumentParser(prog="test")
    parser.set_defaults(handler="invalid")

    with pytest.raises(TypeError, match="not callable"):
        dispatch_cli(parser.parse_args([]), parser)


def test_dispatch_rejects_non_integer_exit_status() -> None:
    parser = argparse.ArgumentParser(prog="test")

    def return_boolean(_args: argparse.Namespace) -> bool:
        return True

    invalid_handler = cast(CliHandler, return_boolean)
    bind_handler(parser, invalid_handler)

    with pytest.raises(TypeError, match="integer exit status"):
        dispatch_cli(parser.parse_args([]), parser)
