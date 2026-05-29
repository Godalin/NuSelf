# Versioning And Changelog Spec

## Purpose

NuSelf should be stabilizable and shareable as a local tool. Versioning and changelog discipline provide a stable way to describe what changed, decide when behavior is safe to rely on, and package releases without relying on memory of recent commits.

## Version Source

- The project version in `pyproject.toml` is the release source of truth.
- Runtime code exposes the installed package version through `nuself.__version__`.
- `nuself.__version__` should read package metadata when available, with a development fallback that matches `pyproject.toml`.
- The daemon protocol version is separate from the package version and remains governed by `src/nuself/daemon/protocol.py`.

## Version Scheme

Use SemVer-like `MAJOR.MINOR.PATCH` versions.

While `MAJOR=0`, minor versions may contain behavior changes. Patch versions should still be reserved for fixes, compatibility repairs, and documentation corrections.

Guidance:

- `PATCH`: stabilization work, refactors, bug fixes, log/output polish, test-only changes, and documentation corrections.
- `MINOR`: a new subsystem or a new cognitive capability that expands the product surface.
- `MAJOR`: a major architecture maturity milestone or an incompatible post-1.0 change.

Branch intent follows the version line:

- `main` tracks the stable, releasable state.
- `dev/0.2.x` tracks stabilization work for the current minor line.
- `feature/*` tracks isolated experiments and should not be treated as release candidates until merged into the stabilization or stable branch.

## Changelog

`CHANGELOG.md` is the human-readable release history.

Format:

```markdown
# Changelog

## Unreleased

### Added
### Changed
### Fixed
### Docs

## 0.1.0 - YYYY-MM-DD
```

Rules:

- User-visible behavior changes should add an entry under `Unreleased`.
- Internal-only refactors may be omitted unless they affect stability, migration, or debugging.
- Release commits move `Unreleased` entries into a dated version section and leave a fresh empty `Unreleased` section.
- The changelog should describe outcomes, not implementation minutiae.

## CLI Version Contract

`nuself --version` prints:

```text
nuself <version>
```

It must not start the daemon, load private memory, or emit startup warnings.

## Release Checklist

TODO before publishing a release:

1. Confirm `uv run pytest`, `uvx pyright`, and `git diff --check`.
2. Move `CHANGELOG.md` `Unreleased` entries to a dated version section.
3. Bump `pyproject.toml` version.
4. Confirm `nuself --version`.
5. Commit with `release: <version>`.
6. Create an annotated tag with `git tag -a v<version> -m "Release <version>"`.
7. When publishing, push the release commit and tag together.

Release tags must point at release metadata commits, not arbitrary feature commits.
