# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Replace the monolithic chat tool module with a subsystem-owned `agent.tools`
package and a thin composition root.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit the monolith's dependency and public-import graph.
2. Specify package ownership and composition boundaries.
3. Extract memory, reflection, reason, trace, selves, and workspace builders.
4. Keep `agent.tools` as the stable public composition entry.
5. Verify subsystem registries and the complete composed registry.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not change tool names, descriptions, schemas, tags, or execution behavior.
- Keep persona tools owned by `nuself.persona`.
- Keep existing public imports from `nuself.agent.tools` working.

## Completion Evidence

- `nuself.agent.tools` is a package whose public `__init__` only constructs
  shared service lifetimes and composes subsystem builders.
- Memory, reflection, reason, trace, selves, and workspace definitions live in
  focused modules; persona definitions remain owned by `nuself.persona`.
- `ReasonAdvancer` imports the public lazy workspace builder instead of a
  private helper.
- Direct subsystem tests verify each builder's exact registry membership.
- A live before/after comparison against `30d48d9` proves all 25 composed tool
  names, order, descriptions, argument schemas, tags, and metadata are equal.
- `.venv/bin/pytest -q`: `1473 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `30d48d9`.

## Next Review Batch

Audit tool dependency lifetime ownership after the registry split.
