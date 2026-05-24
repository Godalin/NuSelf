"""Persona prompt storage — private repo, not memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

from nuself.config import runtime_paths


@dataclass(frozen=True)
class PersonaPrompt:
    """A dynamic thinking persona stored in the private repo."""

    id: str
    name: str
    prompt: str
    created_at: str
    updated_at: str

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> PersonaPrompt:
        return cls(
            id=_expect_str(data, "id"),
            name=_expect_str(data, "name"),
            prompt=_expect_str(data, "prompt"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
        )


def _expect_str(data: dict[str, object], key: str) -> str:
    val = data.get(key)
    if isinstance(val, str):
        return val
    raise ValueError(f"persona prompt field '{key}' must be a string, got {type(val).__name__}")


class PersonaPromptRepository:
    """File-backed repository for dynamic thinking personas.

    By default stores under ``private/persona_prompts/``.
    Pass a custom *root* to scope to a thread workspace.
    """

    def __init__(self, project_root: Path | None = None, *, root: Path | None = None) -> None:
        if root is not None:
            self._root = root
        else:
            paths = runtime_paths(project_root)
            self._root = paths.private_root / "persona_prompts"
        self._is_scoped = root is not None

    # Public API ---------------------------------------------------------------

    def save(self, prompt: PersonaPrompt) -> None:
        """Persist a persona prompt (create or update)."""
        self._ensure_dir()
        self._write_prompt(prompt)
        self._update_name_index(prompt)

    def get(self, prompt_id: str) -> PersonaPrompt | None:
        """Load a prompt by id, or None if missing."""
        path = self._prompt_path(prompt_id)
        if not path.exists():
            return None
        return _read_prompt_file(path)

    def get_by_name(self, name: str) -> PersonaPrompt | None:
        """Look up a prompt by name via the name index."""
        index = self._load_name_index()
        prompt_id = index.get(name)
        if prompt_id is None:
            return None
        return self.get(prompt_id)

    def resolve(self, name_or_id: str) -> PersonaPrompt | None:
        """Resolve by id first, then by name."""
        prompt = self.get(name_or_id)
        if prompt is not None:
            return prompt
        return self.get_by_name(name_or_id)

    def list(self) -> tuple[PersonaPrompt, ...]:
        """Return all stored personas."""
        self._ensure_dir()
        result: list[PersonaPrompt] = []
        for path in sorted(self._root.iterdir()):
            if path.suffix == ".json" and path.name != "name_index.json":
                prompt = _read_prompt_file(path)
                if prompt is not None:
                    result.append(prompt)
        return tuple(result)

    def delete(self, prompt_id: str) -> None:
        """Remove a persona prompt by id."""
        path = self._prompt_path(prompt_id)
        if path.exists():
            path.unlink()
        self._rebuild_name_index()

    # Internals ----------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _prompt_path(self, prompt_id: str) -> Path:
        return self._root / f"{prompt_id}.json"

    def _index_path(self) -> Path:
        return self._root / "name_index.json"

    def _write_prompt(self, prompt: PersonaPrompt) -> None:
        path = self._prompt_path(prompt.id)
        _write_json_atomic(path, prompt.to_wire())

    def _load_name_index(self) -> dict[str, str]:
        path = self._index_path()
        if not path.exists():
            return {}
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw_dict = cast(dict[str, object], raw)
                result: dict[str, str] = {}
                for k, v in raw_dict.items():
                    if isinstance(v, str):
                        result[k] = v
                return result
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _update_name_index(self, prompt: PersonaPrompt) -> None:
        index = self._load_name_index()
        index[prompt.name] = prompt.id
        _write_json_atomic(self._index_path(), cast(dict[str, object], dict(index)))

    def _rebuild_name_index(self) -> None:
        index: dict[str, str] = {}
        for path in self._root.iterdir():
            if path.suffix == ".json" and path.name != "name_index.json":
                prompt = _read_prompt_file(path)
                if prompt is not None:
                    index[prompt.name] = prompt.id
        _write_json_atomic(self._index_path(), cast(dict[str, object], dict(index)))


def _read_prompt_file(path: Path) -> PersonaPrompt | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return PersonaPrompt.from_wire(cast(dict[str, object], raw))
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def create_persona_prompt(name: str, prompt_text: str, *, project_root: Path | None = None) -> PersonaPrompt:
    """Create a new PersonaPrompt with generated id and timestamps."""
    now = datetime.now(UTC).isoformat()
    return PersonaPrompt(
        id=uuid4().hex,
        name=name,
        prompt=prompt_text,
        created_at=now,
        updated_at=now,
    )
