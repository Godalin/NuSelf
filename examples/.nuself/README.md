# Example NuSelf Authority

This directory shows the public, safe-to-commit shape of a NuSelf authority.

Installed NuSelf uses `~/.nuself/` by default. An explicitly selected workspace
uses `<workspace>/.nuself/`; the repository-root instance is ignored by Git.
Real authorities may contain private source material, profile state, and
exports that must not be committed.

Use this example only for documentation and demos. Initialize a real authority
with `nuself init`, `nuself --local init`, or `nuself --workspace PATH init`.
