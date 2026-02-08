# DataM8 Generator

`datam8-generator` contains the DataM8 v2 backend:

- `datam8` CLI
- `datam8 serve` FastAPI server
- in-process Jobs system with SSE event streaming

Neon launches this backend binary and communicates over localhost HTTP.

## Key docs

- Backend contract (canonical): `docs/backend-contract.md`
- Server startup/auth details: `docs/server.md`
- Jobs details: `docs/jobs.md`
- Connector plugin details: `docs/connectors.md`
- Agent guidance: `AGENTS.md`

## Local development

### Requirements
- Python 3.12+
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)

### Clone

```sh
git clone --recurse-submodules https://github.com/oraylis/datam8-generator.git
cd datam8-generator
git submodule update --init --recursive
```

### Run CLI

```sh
uv run datam8 --help
uv run datam8 serve --help
uv run datam8 validate --help
uv run datam8 generate --help
```

### Build package

```sh
uv build
```

### Build backend binaries

Output path:

`dist/bin/<platform>/datam8(.exe)`

Build command:

```sh
uv run python scripts/build_binaries.py
```

### Tests

All tests use local fixtures in this repository.

```sh
uv sync
uv run pytest
```

Fixture used by server/jobs integration tests:

- `tests/fixtures/solutions/minimal-v2/minimal.dm8s`

### Linting / checks

```sh
uv tool run ruff check src
uv tool run pyright src
```
