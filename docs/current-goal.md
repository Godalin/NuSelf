# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Complete the v0.3.1 local-authority upgrade by removing stale checkout-local
configuration terminology and paths, fixing clean-environment CI, and proving
the migrated `./.nuself` runtime and public example are consistent.

## Active Branch

`main`

## Ordered Work

1. [complete] Migrate and verify the checkout authority, delete legacy
   `private/`, and rename the public example.
2. [complete] Fix clean-CI references to the removed example path.
3. [complete] Remove remaining current-runtime `private` terminology from CLI,
   composition helpers, code documentation, and governing current contracts.
4. [complete] Verify the clean checkout, full tests, Pyright, build, wheel smoke, and
   migrated local daemon.
5. [in progress] Commit, push, verify six-platform CI, and return this board to idle.

## Completion Evidence

- Migration and initial cleanup are recorded in `de7abec`.
- CI run `30541909545` found one stale test path:
  `tests/unit/config/config_schema.py` still read
  `examples/private/config.yaml`.
- The failing schema test and 404 related tests pass; full pytest and Pyright
  pass locally.
- Staged sdist/wheel build and clean-wheel import prove `nuself.authority` is
  packaged and obsolete `nuself.private` is absent.
- Migrated local config no longer contains the ignored
  `experimental.langmem_adapter`; `dev config` is warning-free and the local
  daemon is healthy.
