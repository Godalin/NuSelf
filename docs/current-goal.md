# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — seal repositories behind application services.

## Objective

Remove the remaining cross-domain repository call path and enforce that
production consumers cannot import repository implementations outside their
own domain or an explicit composition root.

## Next Steps

1. Specify the repository construction and consumption boundary.
2. Change generic data administration to use `MemoryService` rather than
   `MemoryEntryRepository`.
3. Add an executable import-boundary test and an exact graph-field assertion
   preventing repository exposure.
4. Run focused and full validation, review, and merge through a short PR.

## Exclusions

- Moving repository-owned DTOs and domain errors into dedicated typed modules;
  that belongs to the later typed-storage-contract step.
- Hiding repository construction from same-domain composition modules.
- Replacing repositories inside their owning services.

## Completion Evidence

- No `ApplicationGraph` field is a repository.
- No cross-domain production module imports a concrete `*Repository` except
  an explicit composition root constructing the owning service.
- Data administration updates/deletes Memory only through `MemoryService`.
- Full tests, Pyright, builds, and CI pass.
