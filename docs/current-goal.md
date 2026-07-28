# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent credentials in provider failures from entering diagnostics.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit exception text across response, log, warning, and CLI boundaries.
2. Verify the declared LLM error redaction behavior.
3. Define one shared sensitive-diagnostic text sanitizer.
4. Apply redaction before LLM diagnostic truncation.
5. Verify labeled, header, query, bearer, and raw provider keys are removed.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Provider exceptions still drive availability and retry classification before
  their diagnostic projection is redacted.
- Non-sensitive error context remains visible up to the existing length bound.
- Arbitrary user content is not globally rewritten by this batch.

## Completion Evidence

- `redact_sensitive_text(...)` removes case-insensitive labeled credentials,
  authorization values, bearer credentials, credential query parameters, raw
  OpenAI/Anthropic-style keys, Slack tokens, GitHub tokens, and AWS access-key
  IDs while retaining surrounding diagnostic context.
- `redact_llm_error(...)` accepts either text or an exception, fails safely on
  broken exception renderers, sanitizes before applying the 500-character
  bound, and is used by every agent LLM diagnostic projection.
- LLM diagnostic exceptions suppress the sensitive provider exception context;
  retry and availability decisions continue using the original exception.
- `report_observed_failure(...)` sanitizes the complete compact chain before
  structured persistence and sanitizes its complete fallback warning again,
  including ambient implicit exception context when logging itself fails.
- Focused LLM, agent, chat, and observability suites: `82 passed`.
- Full test suite: `1636 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `6f69634`.

## Next Review Batch

Continue applying the shared diagnostic privacy boundary to non-LLM
infrastructure after provider credentials are protected.
