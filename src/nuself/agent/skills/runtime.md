---
name: runtime
description: Use this skill when the user asks for the current time, date, today, or a relative date that depends on now.
allowed-tools:
  - runtime_time
---

# Runtime Skill

Use {tool:time} whenever the answer materially depends on the current date or
time. Treat its local and UTC timestamps as the authority for “now” and
“today”; do not infer the current time from model knowledge or message history.

For relative-date reasoning, call the Tool once and explain which timezone you
used. Do not call it when time is irrelevant to the user's request.
