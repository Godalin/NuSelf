"""Small deterministic helpers shared by memory agents."""

from __future__ import annotations


def clamp_unit(value: float) -> float:
    return max(0.0, min(value, 1.0))


def extract_json_object(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = [
            line
            for line in stripped.splitlines()
            if not line.strip().startswith("```")
        ]
        stripped = "\n".join(lines).strip()
    return stripped


def looks_like_raw_transcript(text: str) -> bool:
    normalized = text.casefold()
    markers = normalized.count("user:") + normalized.count("assistant:")
    return markers >= 2
