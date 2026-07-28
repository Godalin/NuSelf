"""Evaluation fixture command handler."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from nuself.eval import load_fixtures, run_eval

NOTIFICATION_EVAL_FIXTURE_COUNT = 3


def handle_eval(args: argparse.Namespace) -> int:
    component: str = args.component
    passed_total = 0
    fixture_total = 0

    if component in ("conversations", "all"):
        default_fixtures = (
            Path(__file__).parent.parent.parent
            / "tests"
            / "fixtures"
            / "conversations"
        )
        fixtures_directory = args.fixtures or default_fixtures
        if fixtures_directory.exists():
            fixtures = load_fixtures(fixtures_directory)
            if fixtures:
                with tempfile.TemporaryDirectory() as temporary:
                    results = run_eval(
                        Path(temporary), fixtures_directory
                    )
                passed = sum(
                    1 for result in results if result.passed
                )
                total = len(results)
                passed_total += passed
                fixture_total += total
                print(
                    f"== conversations: {passed}/{total} "
                    "passed =="
                )
                for result in results:
                    status = "PASS" if result.passed else "FAIL"
                    print(
                        f"  {status} {result.fixture_name} "
                        f"(score={result.score:.2f})"
                    )
                    for failure in result.failures:
                        print(f"    - {failure}")
            else:
                print("No conversation fixtures found.")
        else:
            print(
                "Fixtures directory not found: "
                f"{fixtures_directory}",
                file=sys.stderr,
            )

    if component in ("notifications", "all"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_notification_eval_fixtures.py",
                "-v",
            ],
            capture_output=True,
            text=True,
        )
        print("== notifications ==")
        print(result.stdout)
        fixture_total += NOTIFICATION_EVAL_FIXTURE_COUNT
        if result.returncode == 0:
            passed_total += NOTIFICATION_EVAL_FIXTURE_COUNT
        else:
            print(result.stderr, file=sys.stderr)

    print(f"\n{passed_total}/{fixture_total} passed")
    return (
        0
        if passed_total == fixture_total and fixture_total > 0
        else 1
    )
