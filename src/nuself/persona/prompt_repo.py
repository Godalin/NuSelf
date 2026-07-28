"""Persona prompt storage — private repo, not memory."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import cast
from uuid import uuid4

from nuself.config import find_project_root, runtime_paths
from nuself.runtime.observability import decode_observed_record
from nuself.storage import StorageBackend, auto_backend

_REPO_LOCKS_LOCK = threading.Lock()
_REPO_LOCKS: dict[Path, threading.RLock] = {}

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
    """Repository for dynamic thinking personas.

    Two modes:
    * **backend** (primary) — uses a ``StorageBackend`` collection.
    * **legacy_file** (transitional, v0.2.4+) — uses a raw *root* directory
      for thread-scoped workspace personas.
    """

    def __init__(
        self,
        backend: StorageBackend | None = None,
        *,
        root: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        effective_root = (
            project_root
            if project_root is not None
            else find_project_root(root) if root is not None else None
        )
        self._project_root = runtime_paths(effective_root).project_root
        if root is not None:
            self._mode = "legacy_file"
            self._root = root
            self._lock = _lock_for_root(self._root)
        elif backend is not None:
            self._mode = "backend"
            self._col = backend.collection("persona_prompts")
            self._lock = threading.RLock()
        else:
            self._mode = "backend"
            self._col = auto_backend().collection("persona_prompts")
            self._lock = threading.RLock()

    # Public API ---------------------------------------------------------------

    def save(self, prompt: PersonaPrompt) -> None:
        with self._lock:
            if self._mode == "legacy_file":
                self._legacy_save(prompt)
            else:
                self._col.put(prompt.id, prompt.to_wire())

    def get(self, prompt_id: str) -> PersonaPrompt | None:
        if self._mode == "legacy_file":
            return self._legacy_get(prompt_id)
        wire = self._col.get(prompt_id)
        if wire is None:
            return None
        return PersonaPrompt.from_wire(wire)

    def get_by_name(self, name: str) -> PersonaPrompt | None:
        if self._mode == "legacy_file":
            return self._legacy_get_by_name(name)
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
        if self._mode == "legacy_file":
            return self._legacy_list()
        result: list[PersonaPrompt] = []
        for wire in self._col.list():
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
            if self._mode == "legacy_file":
                self._legacy_delete(prompt_id)
            else:
                self._col.delete(prompt_id)

    def set_disabled(self, prompt_id: str, disabled: bool) -> None:
        prompt = self.get(prompt_id)
        if prompt is None:
            return
        updated = prompt.with_updates(disabled=disabled)
        self.save(updated)


    # ── Legacy file-backed mode (root=) ──────────────────────────────────────

    def _legacy_save(self, prompt: PersonaPrompt) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self._root / f"{prompt.id}.json", prompt.to_wire())
        self._legacy_update_name_index(prompt)

    def _legacy_get(self, prompt_id: str) -> PersonaPrompt | None:
        path = self._root / f"{prompt_id}.json"
        if not path.exists():
            return None
        return _read_legacy_prompt_file(path)

    def _legacy_get_by_name(self, name: str) -> PersonaPrompt | None:
        index = self._legacy_load_name_index()
        prompt_id = index.get(name)
        if prompt_id is None:
            return None
        return self._legacy_get(prompt_id)

    def _legacy_list(self) -> tuple[PersonaPrompt, ...]:
        if not self._root.exists():
            return ()
        result: list[PersonaPrompt] = []
        for path in sorted(self._root.iterdir()):
            if path.suffix == ".json" and path.name != "name_index.json":
                prompt = self._decode_legacy_prompt(path)
                if prompt is not None:
                    result.append(prompt)
        return tuple(result)

    def _decode_legacy_prompt(self, path: Path) -> PersonaPrompt | None:
        def decode(_: dict[str, object]) -> PersonaPrompt:
            return _read_legacy_prompt_file(path)

        return decode_observed_record(
            {"id": path.stem},
            decode,
            component="persona",
            collection="persona_prompts",
            project_root=self._project_root,
            errors=(json.JSONDecodeError, ValueError, KeyError, TypeError),
        )

    def _legacy_delete(self, prompt_id: str) -> None:
        path = self._root / f"{prompt_id}.json"
        if path.exists():
            path.unlink()
        self._legacy_rebuild_name_index()

    def _legacy_load_name_index(self) -> dict[str, str]:
        path = self._root / "name_index.json"
        if not path.exists():
            return {}
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                result: dict[str, str] = {}
                for k, v in cast("dict[str, object]", raw).items():
                    if isinstance(v, str):
                        result[k] = v
                return result
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _legacy_update_name_index(self, prompt: PersonaPrompt) -> None:
        index = self._legacy_load_name_index()
        index[prompt.name] = prompt.id
        _write_json_atomic(self._root / "name_index.json", cast("dict[str, object]", dict(index)))

    def _legacy_rebuild_name_index(self) -> None:
        index: dict[str, str] = {}
        for path in self._root.iterdir():
            if path.suffix == ".json" and path.name != "name_index.json":
                prompt = self._decode_legacy_prompt(path)
                if prompt is not None:
                    index[prompt.name] = prompt.id
        _write_json_atomic(self._root / "name_index.json", cast("dict[str, object]", dict(index)))


# ── Helpers ──────────────────────────────────────────────────────────────


def _read_legacy_prompt_file(path: Path) -> PersonaPrompt:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("persona prompt record must be an object")
    return PersonaPrompt.from_wire(cast("dict[str, object]", raw))


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _lock_for_root(root: Path) -> threading.RLock:
    key = root.resolve()
    with _REPO_LOCKS_LOCK:
        lock = _REPO_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _REPO_LOCKS[key] = lock
        return lock


def create_persona_prompt(name: str, prompt_text: str, *, project_root: Path | None = None) -> PersonaPrompt:
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
