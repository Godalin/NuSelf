---
name: reflection
description: Use this skill when the user asks for ideas, thoughts, reflections, or open-ended exploration that may benefit from pending proactive reflection ideas.
---

# Reflection Skill

Reflection ideas are proactive suggestions, not facts about the user.

CRITICAL: When the user asks about pending reflections, ideas, thoughts, or open-ended exploration, you MUST call {tool:list_pending} before answering. Do not list reflections from your training data; always use the tool.

If the user explicitly asks to query, check, list, or inspect pending reflection ideas, call {tool:list_pending} before answering.

Use {tool:list_pending} when the user asks for ideas, thoughts, or reflections, when the conversation naturally pauses, or when the topic strongly matches proactive exploration.

Introduce at most one idea in natural language.

Do not dump the raw reflection list into the answer.

Use {tool:dismiss} when the user declines a topic.

Use {tool:archive} when the user engages and the discussion feels complete.
