"""Chat response schemas, parsing, and user-facing boundary checks."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import TypeAlias, cast

from pydantic import BaseModel, Field


class ChatStructuredOutput(BaseModel):
    """Structured chat response used by LangChain response_format."""

    answer: str = Field(description="Plain user-facing answer text. Do not include internal protocol fields.")
    evidence_references: list[str] = Field(default_factory=list, description="Memory, source, or trace ids used.")
    confidence: float | None = Field(default=None, description="Optional confidence from 0.0 to 1.0.")
    epistemic_status: str = Field(default="inferred", description="One of grounded, inferred, uncertain, unsupported.")


class StructuredOutputError(ValueError):
    """Raised when the agent returns output that cannot be parsed as structured JSON."""

    def __init__(self, raw_text: str) -> None:
        super().__init__(f"LangChain agent returned non-JSON response: {raw_text[:200]!r}")
        self.raw_text = raw_text


@dataclass(frozen=True)
class DraftResponse:
    """Internal substantive response before final presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"

    @property
    def draft_answer(self) -> str:
        return self.answer


@dataclass(frozen=True)
class PresentedResponse:
    """Final user-facing response after presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"


ParsedChatResponse: TypeAlias = DraftResponse

_PROTOCOL_FIELD_NAMES = ("answer", "evidence_references", "confidence", "epistemic_status")
_VISIBLE_TOOL_MARKER_RE = re.compile(r"\[Tool call:\s*[A-Za-z_][A-Za-z0-9_]*\]", re.IGNORECASE)
_TOOL_BLOCK_RE = re.compile(r"\[TOOL_CALL\](?P<body>.*?)\[/TOOL_CALL\]", re.DOTALL | re.IGNORECASE)
_MD_FENCE_JSON_RE = re.compile(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", re.DOTALL)


def _try_extract_md_json(text: str) -> str | None:
    m = _MD_FENCE_JSON_RE.search(text)
    if m is not None:
        return m.group(1)
    return None


def structured_chat_output_to_response(output: object) -> ParsedChatResponse:
    if isinstance(output, ChatStructuredOutput):
        return ParsedChatResponse(
            answer=output.answer,
            evidence_references=tuple(output.evidence_references),
            confidence=output.confidence,
            epistemic_status=output.epistemic_status,
        )
    if isinstance(output, dict):
        data = cast(dict[object, object], output)
        answer = data.get("answer")
        if not isinstance(answer, str):
            raise ValueError("structured chat output did not include answer")
        return ParsedChatResponse(
            answer=answer,
            evidence_references=_string_tuple(data.get("evidence_references")),
            confidence=_optional_float(data.get("confidence")),
            epistemic_status=_string_field(data.get("epistemic_status"), default="inferred") or "inferred",
        )
    raise TypeError(f"unsupported structured chat output: {type(output).__name__}")


def parse_chat_response(raw: str) -> ParsedChatResponse:
    """Parse a plain-text or JSON-envelope LLM response (non-LangChain fallback)."""
    text = raw.strip()
    fenced = _try_extract_md_json(text)
    if fenced is not None:
        text = fenced
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError:
            return ParsedChatResponse(answer=raw)
        if isinstance(parsed, dict):
            data = cast(dict[str, object], parsed)
            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                return ParsedChatResponse(
                    answer=answer,
                    evidence_references=_string_tuple(data.get("evidence_references")),
                    confidence=_optional_float(data.get("confidence")),
                    epistemic_status=_string_field(data.get("epistemic_status"), default="inferred") or "inferred",
                )
            tool = _string_field(data.get("tool"))
            if tool is not None:
                return ParsedChatResponse(answer="")
    return ParsedChatResponse(answer=raw)


def to_presented_response(response: ParsedChatResponse) -> PresentedResponse:
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=response.confidence,
        epistemic_status=response.epistemic_status,
    )


def is_parsed_user_facing_safe(response: ParsedChatResponse) -> bool:
    return not leaks_response_protocol(response.answer)


def presentation_hints(user_message: str) -> tuple[str, ...]:
    normalized = user_message.casefold()
    hints: list[str] = []
    if any(marker in normalized for marker in ("简单", "短", "太多", "想不过来", "simple", "short", "too much")):
        hints.append("The user is asking for a shorter, simpler answer. Prefer compression and one concrete next step.")
    return tuple(hints)


def apply_unsupported_claim_guard(response: PresentedResponse) -> PresentedResponse:
    if response.evidence_references:
        return response
    if not _looks_like_personal_claim(response.answer):
        return response
    confidence = response.confidence if response.confidence is not None else 0.25
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=min(confidence, 0.25),
        epistemic_status="unsupported",
    )


def trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def leaks_response_protocol(answer: str) -> bool:
    stripped = answer.strip()
    if _VISIBLE_TOOL_MARKER_RE.search(stripped) is not None or _TOOL_BLOCK_RE.search(stripped) is not None:
        return True
    if stripped.startswith("```"):
        return True
    if stripped.startswith("{") and _contains_protocol_field(stripped):
        return True
    if _starts_with_persona_attribution(stripped):
        return True
    lowered = stripped[:4000].casefold()
    return sum(1 for field_name in _PROTOCOL_FIELD_NAMES if field_name in lowered) >= 2


def _contains_protocol_field(text: str) -> bool:
    lowered = text[:4000].casefold()
    for field_name in _PROTOCOL_FIELD_NAMES:
        if f'"{field_name}"' in lowered or f"{field_name}:" in lowered:
            return True
    return False


def _starts_with_persona_attribution(text: str) -> bool:
    prefixes = ("(", "（")
    stripped = text.strip()
    if not stripped.startswith(prefixes):
        return False
    head = stripped[:240]
    return "_self" in head and (")" in head or "）" in head)


def _looks_like_personal_claim(answer: str) -> bool:
    normalized = answer.casefold()
    claim_markers = (
        "you ",
        "your ",
        "remember",
        "prefer",
        "like",
        "believe",
        "think",
        "previously",
        "earlier",
        "always",
        "never",
        "history",
        "memory",
    )
    return any(marker in normalized for marker in claim_markers)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item.strip() != "":
            result.append(item.strip())
    return tuple(result)


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_field(value: object, *, default: str | None = None) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return default
