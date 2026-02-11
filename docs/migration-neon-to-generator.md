# Migration Notes: Neon -> Generator Backend

The migration is complete: `datam8-generator` is the backend source of truth for DataM8 v2.

## Current state

- Neon starts `datam8 serve` and communicates over localhost HTTP.
- Backend operations are synchronous HTTP calls (no Jobs/SSE layer).
- Backend behavior and contract are owned by this repository.

## Canonical references

- Backend contract: `docs/backend-contract.md`
- Server behavior: `docs/server.md`

## Contributor guidance

When changing API behavior consumed by Neon:

1. Update `docs/backend-contract.md` first.
2. Implement coordinated backend + Neon changes.
3. Add or adjust tests that cover the real flow (request -> response -> output/state assertions).
