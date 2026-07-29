"""Fail closed when release tag, package metadata, and changelog disagree."""

from __future__ import annotations

import argparse
from pathlib import Path

from nuself.release_gate import check_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        check_release(Path(__file__).resolve().parents[1], args.tag)
    except ValueError as exc:
        parser.error(str(exc))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
