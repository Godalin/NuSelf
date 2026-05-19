---
name: reason
description: Use this skill when the user asks about active long-running questions, open reasoning threads, or what NuSelf is continuing to think about.
allowed-tools:
  - list_active_reasoning_threads
  - show_reasoning_thread
---

# Reason Skill

Reason is NuSelf's durable long-run thinking space.

Use `list_active_reasoning_threads` before answering when the user asks about active long-running questions, open threads, ongoing thinking, or what NuSelf is still considering.

Use `show_reasoning_thread` when the user asks about a specific reasoning thread.

You may suggest creating or advancing a reasoning thread, but must not create, advance, resolve, or archive one without explicit user confirmation.

Do not claim there are no active reasoning threads unless you have called `list_active_reasoning_threads` or the answer is fully present in visible context.
