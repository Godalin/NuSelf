"""Helpers for parsing JSON objects returned by LLMs."""

from __future__ import annotations

import json
from typing import cast


def parse_llm_json_object(raw: str) -> dict[str, object]:
    """Parse an LLM response that should contain one JSON object.

    The helper tolerates Markdown code fences because weaker models sometimes
    ignore "return JSON only" instructions.
    """

    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    parsed: object = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return cast(dict[str, object], parsed)
