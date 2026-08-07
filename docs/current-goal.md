# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — Tool effect architecture cleanup.

## Objective

Resolve the concrete architectural flaws identified after the bound Tool
effect refactor without adding new user-facing capabilities, then document the
resulting decorator and execution model.

## Next Steps

1. Remove duplicate Tool lifecycle projections and establish one observable
   outcome vocabulary.
2. Route feature audit failures through the shared observable best-effort
   boundary and make the weak audit guarantee explicit.
3. Replace exception-as-success-data in daemon Chat scheduling with a typed
   suspension outcome while retaining the effect exception at the executor
   control boundary.
4. Strengthen structural checks that keep `ApplicationGraph` a finite typed
   composition result rather than a service locator.
5. Avoid duplicate CI matrices for the same pull-request commit.
6. Run focused and full verification, review the complete diff, commit each
   independently meaningful step, and prepare a PR into `dev/v0.4.x`.

## Exclusions

- No new Tool effect family, frontend interaction, or domain capability.
- No redesign of the generic wire codec or terminal dispatch.
- No release/tag/version change.
- No broad `ApplicationGraph` decomposition unrelated to enforceable guards.

## Completion Evidence

- Governing specifications describe the final lifecycle, audit, suspension,
  composition, and CI contracts.
- Focused tests cover each corrected boundary.
- Pyright, full pytest, build, clean-wheel smoke, and diff checks pass.
- The branch contains scoped commits and a reviewed PR-ready diff.
