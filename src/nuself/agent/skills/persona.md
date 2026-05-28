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

Personas come in two scopes:
- **Global** — visible to all agents (chat, reason, etc.).
- **Local** — created inside a reasoning thread, visible only to that thread.
  Local personas are listed with a `[local]` tag.

Use {tool:list} to see available personas. In a reasoning thread this
includes both global and thread-scoped personas.

Use {tool:think} when you need a specific persona's take on a question,
subproblem, or hypothesis. The tool searches local personas first,
then falls back to global. This is useful for:
- Testing a hypothesis from a different angle.
- Surfacing blind spots the main reasoning might miss.
- Getting expert-grounded perspective on a specialized subquestion.
- Exploring emotional, ethical, or value-laden dimensions of a topic.

When you get a persona's response, synthesize it naturally into your answer
or reasoning step. Do not dump raw persona output unless the user asks to
inspect it.

In a reasoning thread, do not present a local persona's own utterance,
answer, critique, vote, judgment, or dialogue line unless persona_think was
called for that persona in the same advance. persona_craft creates the persona;
persona_think produces auditable persona speech.

Use {tool:craft} to create a new persona for the current reasoning thread.
The user must explicitly ask for a new persona — do not create one
speculatively. Local personas are private to that thread and not
visible to other threads' persona lists.
