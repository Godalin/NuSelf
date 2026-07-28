# AGENTS.md

NuSelf is a local-first AI mirror for deep personal discussion. This file
defines repository-level development constraints; detailed behavior and policy
belong in the linked authoritative documents.

## Required Workflow

1. **Track the active goal.** Read [`docs/current-goal.md`](docs/current-goal.md)
   before non-trivial work. Define the objective, ordered steps, exclusions,
   and completion evidence before implementation; update them as soon as scope
   or progress changes.
2. **Design before implementation.** Update the governing specification before
   any non-trivial feature or behavioral change. The specification must always
   describe the actual system.
3. **Use framework-native agent APIs.** Prefer official LangChain/LangGraph
   abstractions for agent runtime concerns. NuSelf code should add domain
   behavior, not replace framework contracts.
4. **Keep each change complete.** Commit related code, tests, specification,
   current-goal progress, and documentation together. User-visible changes must
   also update both READMEs and `CHANGELOG.md` under `Unreleased`.
5. **Close the goal cleanly.** Move only unresolved follow-ups to `TODOs.md`;
   preserve completed work in Git or `CHANGELOG.md`, then return
   `current-goal.md` to an explicit idle state.

## Documentation Map

- [`docs/current-goal.md`](docs/current-goal.md) — active execution state
- [`docs/spec/README.md`](docs/spec/README.md) — authoritative specification index
- [`docs/spec/development.md`](docs/spec/development.md) — detailed development, commit, and release policy
- [`docs/architecture.md`](docs/architecture.md) — current system boundaries and rationale
- [`docs/TODOs.md`](docs/TODOs.md) — unresolved medium/long-term backlog
- [`CHANGELOG.md`](CHANGELOG.md) — completed user-visible changes

Behavioral conflicts are resolved in the governing specification; development
process conflicts are resolved in `docs/spec/development.md`. Correct the
outdated document in the same change.
