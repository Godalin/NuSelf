---
name: persona
description: Load this skill when the reasoning or answer would benefit from an internal persona's perspective on a subproblem, blind-spot analysis, or alternative viewpoint.
allowed-tools:
  - persona_list
  - persona_think
  - persona_craft
---

# Persona Skill

Personas are reusable thinking perspectives inside NuSelf — each one represents a distinct cognitive stance, expertise area, or viewpoint.

Use {tool:list} to see which personas are available.

Use {tool:think} when you need a specific persona's take on a question, subproblem, or hypothesis. This is useful for:
- Testing a hypothesis from a different angle.
- Surfacing blind spots the main reasoning might miss.
- Getting expert-grounded perspective on a specialized subquestion.
- Exploring emotional, ethical, or value-laden dimensions of a topic.

When you get a persona's response, synthesize it naturally into your answer or reasoning step. Do not dump raw persona output unless the user asks to inspect it.

Use {tool:craft} to create a new persona when the user wants a specific perspective that doesn't exist yet. The user must explicitly ask for a new persona — do not create one speculatively.
