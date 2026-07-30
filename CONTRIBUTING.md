# Contributing

NuSelf is under active development. Keep changes small enough to review but
complete across code, tests, specifications, and user documentation.

## Set Up

Requirements:

- Python 3.12 or newer on Linux or macOS
- uv `0.11.21`

Install the locked development environment:

```bash
uv sync --locked --group dev
```

## Required Workflow

Read [`AGENTS.md`](AGENTS.md) and
[`docs/current-goal.md`](docs/current-goal.md) before non-trivial work.

1. Define the active objective, ordered work, exclusions, and completion
   evidence.
2. Update the governing specification before a behavioral change.
3. Implement the complete repository-wide change without compatibility shims
   unless a persisted-data or wire migration requires one.
4. Add tests and update both READMEs plus `CHANGELOG.md` for user-visible
   behavior.
5. Commit coherent functional boundaries.
6. Return `docs/current-goal.md` to an explicit idle state when finished.

Detailed development and release policy lives in
[`docs/spec/development.md`](docs/spec/development.md).

## Validate

Run the normal local gates:

```bash
uv lock --check
uv run --locked pyright
uv run --locked pytest
git diff --check
```

Build distributions when changing packaging or release infrastructure:

```bash
uv build
```

The default suite is deterministic and does not call real model providers.
See [`tests/README.md`](tests/README.md) for layout and focused commands.

## Live Provider Tests

Real-provider tests are explicit, network- and cost-bearing:

```bash
uv run --locked pytest tests/live -m live_api --run-live-api
```

They send fixed synthetic prompts and never load project-private memory or
threads. See [`tests/live/README.md`](tests/live/README.md) before running a
provider or model matrix.

## Specifications And Documentation

- [`docs/spec/README.md`](docs/spec/README.md) indexes authoritative behavior.
- [`docs/architecture.md`](docs/architecture.md) explains current boundaries
  and rationale.
- [`docs/configuration.md`](docs/configuration.md),
  [`docs/cli.md`](docs/cli.md), and [`docs/memory.md`](docs/memory.md) are
  user-facing guides.
- [`CHANGELOG.md`](CHANGELOG.md) records completed user-visible changes.
- [`docs/TODOs.md`](docs/TODOs.md) contains unresolved medium- and long-term
  work.

Do not duplicate implementation contracts in the README. Update the
authoritative spec and link to it from the appropriate guide.

## Commit Policy

Use imperative, scoped messages where useful, for example:

```text
docs: simplify project readme
fix(storage): serialize schema upgrades
test(chat): cover provider failover
release: 0.3.0
```

Every commit should leave its functional boundary internally consistent.
