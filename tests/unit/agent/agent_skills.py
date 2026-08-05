"""Tests for Agent Skills loading."""

from __future__ import annotations

from nuself.agent.skill_loader import load_agent_skills


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
    assert "memory_create" in skills["memory"].allowed_tools
    assert "reflection_list_pending" in skills["reflection"].allowed_tools
    assert "selves_consult" in skills["selves"].allowed_tools
    assert "trace_search" in skills["trace"].allowed_tools
    assert "trace_related" in skills["trace"].allowed_tools
    assert "reason_export" in skills["reason_output"].allowed_tools
    assert "Call `reason_export` directly" in skills["reason_output"].instructions
    assert "workspace_put" in skills["workspace"].allowed_tools
    assert "reason_propose" in skills["reason_proposal"].allowed_tools
    assert "advance at most one complete round per step" in skills["reason_proposal"].instructions
    assert "persona-grounding mandate" in skills["reason_proposal"].instructions
    assert "persona_think produces auditable persona speech" in skills["persona"].instructions
    assert "valid JSON string" in skills["workspace"].instructions
