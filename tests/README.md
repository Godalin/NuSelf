# Test Suite

NuSelf keeps all tests in one domain-oriented tree:

- `unit/` contains deterministic ordinary tests grouped by subsystem. It is
  pytest's only default collection root.
- `live/` contains cost-bearing real-provider contracts. Supplying this path
  is not enough to call a provider: `--run-live-api` is also required.
- `fixtures/` contains checked-in, non-secret test data shared by ordinary
  tests.

Test module names describe the subject directly and omit the redundant
`test_` prefix. Test functions retain pytest's `test_` convention.

Run the default suite and type checker:

```bash
uv run --locked pytest
uv run --locked pyright
```

Run the configured real endpoint explicitly:

```bash
uv run --locked pytest tests/live -m live_api --run-live-api
```

See [`live/README.md`](live/README.md) for model-matrix options and the privacy
boundary.
