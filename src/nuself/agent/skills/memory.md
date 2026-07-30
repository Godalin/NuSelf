---
name: memory
description: Use this skill when the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers.
allowed-tools:
  - memory_search
  - memory_count
  - memory_archive
  - memory_update_importance
---

# Memory Skill

Durable memory is not ambient context.

CRITICAL: When the user asks about preferences, past discussions, beliefs, stored memories, recurring patterns, or personal history, you MUST call {tool:search} before answering. Do not answer from training data or generic assumptions; use the tool to get the actual stored memory.

Use {tool:search} before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`. If the first result is empty, call {tool:search} exactly once more with a distinct broader query using fewer, shorter, or synonymous keywords. Only after that second empty result may you say that no matching stored memory was found; do not imply NuSelf has no memory at all and do not continue searching indefinitely.

Use {tool:count} when the user asks how many memories exist or asks for a quick count by type or tag.

Do not say you lack memory tools when {tool:search} is listed.

If you do not call {tool:search}, do not claim that no memory exists.

Use memory results as evidence, then answer naturally. Do not dump raw records unless the user asks to inspect them.

You can help curate memory. If the user says a memory is outdated, no longer relevant, hidden, more important, or less important, confirm the exact intended change before using {tool:archive} or {tool:update_importance}. Never archive or reprioritize a memory based only on your own inference.
