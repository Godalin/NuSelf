# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make the reason tool pipeline framework-typed end to end and remove dynamic
metadata probing from `ReasonAdvancer`.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify `BaseTool` and metadata transfer contracts.
2. Replace `Sequence[Any]` and tool tuples of `Any`.
3. Remove `hasattr` metadata probing.
4. Validate `service_component` before internal log transfer.
5. Verify explicit tools retain identity and valid metadata.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep compiled LangGraph agent objects typed as `Any` at the untyped framework
  boundary.
- Keep tools without service metadata valid.

## Completion Evidence

- The capability snapshot, scheduler, factory, advancer, workspace builders,
  and persona builders now carry `BaseTool` values end to end.
- The reason tool path no longer uses `Sequence[Any]`, tool tuples of `Any`, or
  dynamic `hasattr(..., "metadata")` probing.
- Explicitly injected tools retain object identity through
  `default_reason_advancer`.
- Only string-valued `metadata["service_component"]` entries enter the
  advancer's internal service route map; missing and invalid metadata remain
  valid and fall back to the default component.
- `.venv/bin/pytest -q`: `1468 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `f3ce385`.

## Next Review Batch

Move `service_component` extraction into shared tool metadata infrastructure
instead of repeating dictionary interpretation.
