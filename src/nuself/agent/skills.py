"""Agent Skills specification loader for NuSelf chat services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml


@dataclass(frozen=True)
class AgentSkill:
    """One SKILL.md file following the Agent Skills directory convention."""

    name: str
    description: str
    instructions: str
    allowed_tools: tuple[str, ...]
    path: Path


def load_agent_skills(root: Path | None = None) -> tuple[AgentSkill, ...]:
    """Load Agent Skills from skill directories."""

    skills_root = root or Path(__file__).parent / "skills"
    if not skills_root.exists():
        return ()
    skills: list[AgentSkill] = []
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            continue
        skills.append(_load_skill_file(skill_path))
    return tuple(skills)


SKILL_SERVICE_MAP: dict[str, str] = {
    "memory": "memory",
    "reflection": "reflection",
    "reason": "reasoning",
    "trace": "trace",
}


def render_agent_skill_sections(
    skills: tuple[AgentSkill, ...],
    *,
    allowed_tools_by_skill: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Render loaded Agent Skills for the current prompt builder.

    When *allowed_tools_by_skill* is provided, allowed-tool lines are
    generated from the actual tool registry rather than from SKILL.md YAML
    frontmatter.
    """

    if not skills:
        return []
    lines = [
        "",
        "Service skills:",
        "The following service skills are loaded from Agent Skills SKILL.md files.",
    ]
    for skill in skills:
        lines.append(f"- {skill.name}: {skill.description}")
        tools = (allowed_tools_by_skill or {}).get(skill.name, skill.allowed_tools)
        if tools:
            lines.append(f"  Allowed tools: {', '.join(tools)}")
        for line in skill.instructions.splitlines():
            if line.strip():
                lines.append(f"  {line}")
    return lines


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
