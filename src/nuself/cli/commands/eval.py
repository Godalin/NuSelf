"""Evaluation fixture command handler."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from nuself.evaluation.suite import EvalResult, load_fixtures, run_eval
from nuself.notification.eval import run_notification_eval


def handle_eval(args: argparse.Namespace) -> int:
    component: str = args.component
    passed_total = 0
    fixture_total = 0

    if component in ("conversations", "all"):
        default_fixtures = _repository_root() / "tests" / "fixtures" / "conversations"
        fixtures_directory = args.fixtures or default_fixtures
        if fixtures_directory.exists():
            fixtures = load_fixtures(fixtures_directory)
            if fixtures:
                with tempfile.TemporaryDirectory() as temporary:
                    results = run_eval(
                        Path(temporary), fixtures_directory
                    )
                passed, total = _result_counts(results)
                passed_total += passed
                fixture_total += total
                _print_results("conversations", results)
            else:
                print("No conversation fixtures found.")
        else:
            print(
                "Fixtures directory not found: "
                f"{fixtures_directory}",
                file=sys.stderr,
            )

    if component in ("notifications", "all"):
        notifications_directory = (
            _repository_root()
            / "tests"
            / "fixtures"
            / "notifications"
        )
        if notifications_directory.exists():
            with tempfile.TemporaryDirectory() as temporary:
                results = run_notification_eval(
                    Path(temporary),
                    notifications_directory,
                )
            passed, total = _result_counts(results)
            passed_total += passed
            fixture_total += total
            _print_results("notifications", results)
        else:
            print(
                "Fixtures directory not found: "
                f"{notifications_directory}",
                file=sys.stderr,
            )

    print(f"\n{passed_total}/{fixture_total} passed")
    return (
        0
        if passed_total == fixture_total and fixture_total > 0
        else 1
    )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _result_counts(results: list[EvalResult]) -> tuple[int, int]:
    return (
        sum(1 for result in results if result.passed),
        len(results),
    )


def _print_results(
    component: str,
    results: list[EvalResult],
) -> None:
    passed, total = _result_counts(results)
    print(f"== {component}: {passed}/{total} passed ==")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"  {status} {result.fixture_name} "
            f"(score={result.score:.2f})"
        )
        for failure in result.failures:
            print(f"    - {failure}")
