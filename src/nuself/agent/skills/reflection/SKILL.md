---
name: reflection
description: Use this skill when the user asks for ideas, thoughts, reflections, or open-ended exploration that may benefit from pending proactive reflection ideas.
---

# Reflection Skill

Reflection ideas are proactive suggestions, not facts about the user.

CRITICAL: When the user asks about pending reflections, ideas, thoughts, or open-ended exploration, you MUST call `list_pending_reflections` before answering. Do not list reflections from your training data; always use the tool.

If the user explicitly asks to query, check, list, or inspect pending reflection ideas, call `list_pending_reflections` before answering.

Use `list_pending_reflections` when the user asks for ideas, thoughts, or reflections, when the conversation naturally pauses, or when the topic strongly matches proactive exploration.

Introduce at most one idea in natural language.

Do not dump the raw reflection list into the answer.

Use `dismiss_reflection` when the user declines a topic.

Use `archive_reflection` when the user engages and the discussion feels complete.
