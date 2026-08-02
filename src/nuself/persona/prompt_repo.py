"""Persona prompt storage — private repo, not memory."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import threading
from uuid import uuid4

from nuself.config import RuntimePaths
from nuself.runtime.observability import decode_observed_record
from nuself.storage import StorageCollection

# ── Unified ID prefix for persona prompts ──────────────────────────────
ID_PREFIX = "pp"


def _generate_id() -> str:
    return f"{ID_PREFIX}_{uuid4().hex}"


@dataclass(frozen=True)
class PersonaPrompt:
    """A dynamic thinking persona stored in the private repo."""

    id: str
    name: str
    prompt: str
    created_at: str
    updated_at: str
    disabled: bool = False

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "disabled": self.disabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> PersonaPrompt:
        disabled_val = data.get("disabled", False)
        disabled = bool(disabled_val) if isinstance(disabled_val, bool) else False
        return cls(
            id=_expect_str(data, "id"),
            name=_expect_str(data, "name"),
            prompt=_expect_str(data, "prompt"),
            disabled=disabled,
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
        )

    def with_updates(self, *, disabled: bool | None = None) -> PersonaPrompt:
        kw: dict[str, object] = {"updated_at": utc_now_iso()}
        if disabled is not None:
            kw["disabled"] = disabled
        return dataclasses.replace(self, **kw)  # pyright: ignore[reportArgumentType]


def _expect_str(data: dict[str, object], key: str) -> str:
    val = data.get(key)
    if isinstance(val, str):
        return val
    raise ValueError(f"persona prompt field '{key}' must be a string, got {type(val).__name__}")


class PersonaPromptRepository:
    """Repository for dynamic thinking personas over one collection protocol."""

    def __init__(
        self,
        collection: StorageCollection,
        paths: RuntimePaths,
    ) -> None:
        self._project_root = paths.authority_root
        self._collection = collection
        self._lock = threading.Lock()

    # Public API ---------------------------------------------------------------

    def save(self, prompt: PersonaPrompt) -> None:
        with self._lock:
            self._collection.put(prompt.id, prompt.to_wire())

    def get(self, prompt_id: str) -> PersonaPrompt | None:
        wire = self._collection.get(prompt_id)
        if wire is None:
            return None
        return PersonaPrompt.from_wire(wire)

    def get_by_name(self, name: str) -> PersonaPrompt | None:
        for p in self.list():
            if p.name == name:
                return p
        return None

    def resolve(self, name_or_id: str) -> PersonaPrompt | None:
        prompt = self.get(name_or_id)
        if prompt is not None:
            return prompt
        return self.get_by_name(name_or_id)

    def list(self) -> tuple[PersonaPrompt, ...]:
        result: list[PersonaPrompt] = []
        for wire in self._collection.list():
            prompt = decode_observed_record(
                wire,
                PersonaPrompt.from_wire,
                component="persona",
                collection="persona_prompts",
                project_root=self._project_root,
            )
            if prompt is not None:
                result.append(prompt)
        return tuple(sorted(result, key=lambda p: p.name))

    def delete(self, prompt_id: str) -> None:
        with self._lock:
            self._collection.delete(prompt_id)

    def set_disabled(self, prompt_id: str, disabled: bool) -> None:
        prompt = self.get(prompt_id)
        if prompt is None:
            return
        updated = prompt.with_updates(disabled=disabled)
        self.save(updated)


def create_persona_prompt(name: str, prompt_text: str) -> PersonaPrompt:
    """Create a new PersonaPrompt with generated id and timestamps."""
    now = utc_now_iso()
    return PersonaPrompt(
        id=_generate_id(),
        name=name,
        prompt=prompt_text,
        created_at=now,
        updated_at=now,
    )
from nuself.clock import utc_now_iso
