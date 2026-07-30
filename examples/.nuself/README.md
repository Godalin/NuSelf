# Example NuSelf Authority

This directory contains only public configuration and source examples.

Installed NuSelf uses `~/.nuself/` by default. An explicitly selected workspace
uses `<workspace>/.nuself/`; the repository-root instance is ignored by Git.
Real authorities also contain `nuself.sqlite`, logs, runtime coordination,
private sources, exports, and backups that must not be committed. Structured
profile, memory, chat, reason, trace, reflection, and scheduler state lives in
SQLite; it is not represented by example JSON or Markdown state files.

Use this example only for documentation and demos. Initialize a real authority
with `nuself init`, `nuself --local init`, or `nuself --workspace PATH init`.
