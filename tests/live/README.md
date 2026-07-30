# Live LLM API Tests

These tests send fixed synthetic prompts to the LLM endpoints configured in
the selected authority's `config.yaml`. They never load NuSelf threads, memory, personas,
sources, or runtime prompts.

They are outside the default pytest collection root and also require an
explicit network/cost opt-in:

```bash
uv run --locked pytest tests/live -m live_api --run-live-api
```

Running `uv run --locked pytest` or normal CI does not collect this directory.
The suite checks raw transport, structured output, ordinary NuSelf chat, and
the production-critical combination of tool calling plus a structured final
response. Failures are reported through NuSelf's credential-redacting LLM
diagnostic formatter.

The maintained OpenCode Go matrix is explicit and cost-bearing:

```bash
uv run --locked pytest tests/live -m live_api --run-live-api \
  --live-opencode-go-matrix
```

It covers representative OpenAI-compatible and Anthropic Messages models.
Strict xfails describe stable unsupported capability layers; non-strict xfails
retain observed unstable layers. Repeat `--live-model provider:model` to test
custom models with every layer required.
