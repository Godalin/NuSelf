from __future__ import annotations

import argparse
from typing import cast

import pytest

from nuself.cli.handlers import (
    CliHandler,
    CliHandlerBindings,
    dispatch_cli,
)
from nuself.cli.readiness import NO_READINESS
from nuself.runtime.handlers import DuplicateHandlerError


def test_bind_handler_dispatches_typed_exit_status() -> None:
    parser = argparse.ArgumentParser(prog="test")
    bindings = CliHandlerBindings()
    bindings.bind(
        parser,
        lambda _args: 7,
        requirements=NO_READINESS,
    )
    bindings.seal(parser)

    assert dispatch_cli(parser.parse_args([]), parser) == 7


def test_bind_help_prints_selected_parser_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = argparse.ArgumentParser(prog="test")
    subparsers = parser.add_subparsers(dest="command")
    group_parser = subparsers.add_parser("group")
    bindings = CliHandlerBindings()
    bindings.bind_help(group_parser)
    bindings.seal(parser)

    assert dispatch_cli(parser.parse_args(["group"]), parser) == 0
    assert capsys.readouterr().out.startswith("usage: test group")


def test_dispatch_rejects_missing_registry() -> None:
    parser = argparse.ArgumentParser(prog="test")
    parser.set_defaults(handler_key="test")

    with pytest.raises(TypeError, match="registry is missing"):
        dispatch_cli(parser.parse_args([]), parser)


def test_dispatch_rejects_non_integer_exit_status() -> None:
    parser = argparse.ArgumentParser(prog="test")

    def return_boolean(_args: argparse.Namespace) -> bool:
        return True

    invalid_handler = cast(CliHandler, return_boolean)
    bindings = CliHandlerBindings()
    bindings.bind(
        parser,
        invalid_handler,
        requirements=NO_READINESS,
    )
    bindings.seal(parser)

    with pytest.raises(TypeError, match="integer exit status"):
        dispatch_cli(parser.parse_args([]), parser)


def test_bindings_reject_duplicate_parser_key() -> None:
    parser = argparse.ArgumentParser(prog="test")
    bindings = CliHandlerBindings()
    bindings.bind(parser, lambda _args: 0)

    with pytest.raises(DuplicateHandlerError):
        bindings.bind(parser, lambda _args: 1)


def test_parsed_namespace_contains_key_not_callable() -> None:
    parser = argparse.ArgumentParser(prog="test")
    bindings = CliHandlerBindings()
    bindings.bind(parser, lambda _args: 0)
    bindings.seal(parser)

    args = parser.parse_args([])

    assert vars(args)["handler_key"] == "test"
    assert all(not callable(value) for value in vars(args).values())
