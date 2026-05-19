"""Tests for Agent Skills loading."""

from __future__ import annotations

from nuself.agent.skills import load_agent_skills, render_agent_skill_sections


def test_load_agent_skills_from_skill_md_files() -> None:
    skills = {skill.name: skill for skill in load_agent_skills()}

    assert "memory" in skills
    assert "reflection" in skills
    assert "reason" in skills
    assert "trace" in skills
    assert "search_memory" in skills["memory"].allowed_tools
    assert "list_pending_reflections" in skills["reflection"].allowed_tools
    assert "list_active_reasoning_threads" in skills["reason"].allowed_tools
    assert "search_trace" in skills["trace"].allowed_tools
    assert "Durable memory is not ambient context" in skills["memory"].instructions


def test_render_agent_skill_sections() -> None:
    skills = load_agent_skills()

    lines = render_agent_skill_sections(skills)

    assert "Service skills:" in lines
    assert any(line.startswith("- memory:") for line in lines)
    assert any("Allowed tools: search_memory" in line for line in lines)
    assert any("Durable memory is not ambient context." in line for line in lines)
