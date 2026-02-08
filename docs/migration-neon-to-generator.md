# Migration Notes: Neon -> Generator Backend

The migration is complete: `datam8-generator` is the backend source of truth for DataM8 v2.

## Current state

- Neon starts `datam8 serve` and communicates over localhost HTTP.
- Long-running operations are Jobs with SSE streaming.
- Backend behavior and contract are owned by this repository.

## Canonical references

- Backend contract: `docs/backend-contract.md`
- Server behavior: `docs/server.md`
- Jobs behavior: `docs/jobs.md`

## Contributor guidance

When changing API behavior consumed by Neon:

1. Update `docs/backend-contract.md` first.
2. Implement coordinated backend + Neon changes.
3. Add/adjust tests that cover the real flow (`POST /jobs` + SSE completion where relevant).
