# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — align concrete code with domain ownership, then stop.

## Objective

Keep shared architectural packages neutral and move concrete composition,
models, workflows, and evaluation code into their owning domains.

## Next Steps

1. Move Chat, Memory, Persona, Reason, Reflection, and Trace composition out of
   `application` and into their owning packages.
2. Move concrete models out of the horizontal `domain` package.
3. Rename concrete `runtime` modules and the Skill loader by their actual
   responsibility; rename the CLI graph-borrowing module accurately.
4. Move Reason export and Notification evaluation into their domains, enforce
   the resulting boundaries, run full gates, and return this board to Idle.

## Exclusions

- Do not change storage layout, conversation structure, daemon scheduling,
  persisted schemas, wire protocols, CLI commands, or user-visible behavior.
- Do not add base-class frameworks, registries, facades, service locators,
  compatibility imports, or plugin machinery.
- Do not continue structural review after the four approved stages.

## Last Verification

- Stage 1: concrete Chat, Memory, Persona, Reason, Reflection, and Trace
  composition now belongs to those packages. `application` fell from twelve to
  five modules and retains only graph composition, lifecycle, data admin, and
  cross-domain knowledge projection. Pyright: 0 errors, 0 warnings; affected
  domain/application/CLI/storage suite: 1017 passed.
- Stage 2: Memory, Profile, Source, and proactive Reflection models now live in
  their owning packages; the horizontal `nuself.domain` package is removed.
  Domain composition receives explicit capabilities rather than importing
  `ApplicationGraph`. Pyright: 0 errors, 0 warnings; affected boundary/domain/
  Chat/CLI suite: 959 passed.
- Stage 3: concrete execution owners are named by responsibility:
  `application.lifecycle`, `agent.chat.engine`, `cli.repl.loop`,
  `agent.skill_loader`, and `cli.application`. No compatibility modules remain.
  Pyright: 0 errors, 0 warnings; focused regression and boundary suite: 56
  passed (the broader affected suite reached 914 passing tests before exposing
  and correcting stale test paths and one outdated test double).
