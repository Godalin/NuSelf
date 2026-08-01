"""Small deterministic helpers shared by memory agents."""

from __future__ import annotations

def looks_like_raw_transcript(text: str) -> bool:
    normalized = text.casefold()
    markers = normalized.count("user:") + normalized.count("assistant:")
    return markers >= 2
