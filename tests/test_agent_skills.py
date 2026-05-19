"""Tests for Agent Skills loading."""

from __future__ import annotations

from nuself.agent.skills import load_agent_skills, render_agent_skill_sections


def test_load_agent_skills_from_skill_md_files() -> None:
    skills = {skill.name: skill for skill in load_agent_skills()}

    assert "memory" in skills
    assert "reflection" in skills
    assert "reason" in skills
    assert "trace" in skills
    assert "Durable memory is not ambient context" in skills["memory"].instructions


def test_render_agent_skill_sections_with_generated_allowed_tools() -> None:
    skills = load_agent_skills()

    allowed_tools_by_skill = {
        "memory": ("search_memory", "archive_memory", "update_memory_importance"),
        "reflection": ("list_pending_reflections", "dismiss_reflection", "archive_reflection"),
        "reason": ("list_active_reasoning_threads", "show_reasoning_thread"),
        "trace": ("search_trace", "show_trace"),
    }
    lines = render_agent_skill_sections(skills, allowed_tools_by_skill=allowed_tools_by_skill)

    assert "Service skills:" in lines
    assert any(line.startswith("- memory:") for line in lines)
    assert any("Allowed tools: search_memory" in line for line in lines)
    assert any("Durable memory is not ambient context." in line for line in lines)


def test_render_agent_skill_sections_works_without_generated_tools() -> None:
    skills = load_agent_skills()

    lines = render_agent_skill_sections(skills)

    assert "Service skills:" in lines
    assert any(line.startswith("- reflection:") for line in lines)
