"""Tests for Agent Skills loading."""

from __future__ import annotations

from nuself.agent.skills import load_agent_skills, render_agent_skill_sections


def test_load_agent_skills_from_flat_markdown_files() -> None:
    skills = {skill.name: skill for skill in load_agent_skills()}

    assert "memory" in skills
    assert "reflection" in skills
    assert "reason" in skills
    assert "reason_proposal" in skills
    assert "trace" in skills
    assert "selves" in skills
    assert "Durable memory is not ambient context" in skills["memory"].instructions
    assert "memory_search" not in skills["memory"].instructions
    assert "{tool:search}" in skills["memory"].instructions
    assert "memory_search" in skills["memory"].allowed_tools
    assert "reflection_list_pending" in skills["reflection"].allowed_tools
    assert "selves_consult" in skills["selves"].allowed_tools
    assert "trace_search" in skills["trace"].allowed_tools
    assert "trace_related" in skills["trace"].allowed_tools
    assert "workspace_put" in skills["workspace"].allowed_tools
    assert "reason_propose" in skills["reason_proposal"].allowed_tools
    assert "advance at most one complete round per step" in skills["reason_proposal"].instructions
    assert "persona-grounding mandate" in skills["reason_proposal"].instructions
    assert "persona_think produces auditable persona speech" in skills["persona"].instructions
    assert "valid JSON string" in skills["workspace"].instructions


def test_render_agent_skill_sections_with_generated_allowed_tools() -> None:
    skills = load_agent_skills()

    allowed_tools_by_skill = {
        "memory": ("memory_search", "memory_count", "memory_archive", "memory_update_importance"),
        "reflection": ("reflection_list_pending", "reflection_count", "reflection_dismiss", "reflection_archive"),
        "reason": ("reason_list_active", "reason_count", "reason_context", "reason_step", "reason_show"),
        "reason_proposal": ("reason_propose",),
        "trace": ("trace_search", "trace_count", "trace_show", "trace_related"),
        "selves": ("selves_consult",),
    }
    lines = render_agent_skill_sections(skills, allowed_tools_by_skill=allowed_tools_by_skill)

    assert "Service skills:" in lines
    assert any(line.startswith("- memory:") for line in lines)
    assert any("Allowed tools: memory_search" in line for line in lines)
    assert any("MUST call `memory_search` before answering" in line for line in lines)
    assert any("Use `reflection_list_pending` when" in line for line in lines)
    assert any("Call `reason_propose` only after" in line for line in lines)
    assert any("Use `selves_consult` when" in line for line in lines)
    assert all("{tool:" not in line for line in lines)
    assert any("Durable memory is not ambient context." in line for line in lines)


def test_render_agent_skill_sections_works_without_generated_tools() -> None:
    skills = load_agent_skills()

    lines = render_agent_skill_sections(skills)

    assert "Service skills:" in lines
    assert any(line.startswith("- reflection:") for line in lines)
