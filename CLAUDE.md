# CLAUDE.md

Quick context for AI/code agents in `datam8-generator`.

## Repository role

`datam8-generator` is the canonical DataM8 v2 backend:
- `datam8` CLI
- `datam8 serve` FastAPI app
- Jobs + SSE for long-running operations

## Canonical references

- Agent rules: `AGENTS.md`
- Backend contract: `docs/backend-contract.md`
- Server details: `docs/server.md`
- Jobs details: `docs/jobs.md`

## Testing

Use a valid sample solution path (e.g. `datam8-sample-solution/ORAYLISDatabricksSample.dm8s`).

Run:

```sh
uv sync
uv run pytest --solution-path "<path-to-solution.dm8s>"
```
