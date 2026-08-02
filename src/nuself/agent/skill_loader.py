"""Agent Skills specification loader for NuSelf chat services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import cast

import yaml

TOOL_PLACEHOLDER_RE = re.compile(r"\{tool:([a-z0-9_]+)\}")


@dataclass(frozen=True)
class AgentSkill:
    """One flat Markdown skill file."""

    name: str
    description: str
    instructions: str
    allowed_tools: tuple[str, ...]
    path: Path


def load_agent_skills(root: Path | None = None) -> tuple[AgentSkill, ...]:
    """Load Agent Skills from flat Markdown files."""

    skills_root = root or Path(__file__).parent / "skills"
    if not skills_root.exists():
        return ()
    skills: list[AgentSkill] = []
    for skill_path in sorted(skills_root.glob("*.md")):
        skills.append(_load_skill_file(skill_path))
    return tuple(skills)


def render_tool_placeholders(instructions: str, *, skill_name: str, tools: tuple[str, ...]) -> str:
    def replace(match: re.Match[str]) -> str:
        action = match.group(1)
        tool_name = _resolve_tool_placeholder(skill_name=skill_name, action=action, tools=tools)
        return f"`{tool_name}`"

    return TOOL_PLACEHOLDER_RE.sub(replace, instructions)


def _resolve_tool_placeholder(*, skill_name: str, action: str, tools: tuple[str, ...]) -> str:
    exact = f"{skill_name}_{action}"
    if exact in tools:
        return exact
    suffix = f"_{action}"
    for tool in tools:
        if tool.endswith(suffix):
            return tool
    return exact


def _load_skill_file(path: Path) -> AgentSkill:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"skill file missing frontmatter: {path}")
    try:
        end_index = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"skill file missing frontmatter terminator: {path}") from exc
    raw_frontmatter = yaml.safe_load("\n".join(lines[1:end_index]))
    if not isinstance(raw_frontmatter, dict):
        raise ValueError(f"skill frontmatter must be a mapping: {path}")
    frontmatter = cast(dict[object, object], raw_frontmatter)
    name = _required_string(frontmatter, "name", path)
    description = _required_string(frontmatter, "description", path)
    allowed_tools = _string_tuple(frontmatter.get("allowed-tools"))
    instructions = "\n".join(lines[end_index + 1 :]).strip()
    return AgentSkill(
        name=name,
        description=description,
        instructions=instructions,
        allowed_tools=allowed_tools,
        path=path,
    )


def _required_string(frontmatter: dict[object, object], key: str, path: Path) -> str:
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"skill frontmatter field {key!r} must be a non-empty string: {path}")
    return value.strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list):
        result: list[str] = []
        for item in cast(list[object], value):
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
        return tuple(result)
    return ()
