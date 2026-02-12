# DataM8 Generator

`datam8-generator` is the canonical DataM8 v2 backend:

- `datam8` CLI
- `datam8 serve` FastAPI server
- synchronous HTTP execution (no Jobs/SSE layer)

Neon launches the backend over embedded Python (`python -m datam8 serve`) and communicates via localhost HTTP.

## Issues

Issues are tracked centrally in the DataM8 repository:

- https://github.com/oraylis/datam8/issues

## Key docs

- Backend contract (canonical): `docs/backend-contract.md`
- Server startup/auth details: `docs/server.md`
- Connector plugin details: `docs/connectors.md`
- Agent guidance: `AGENTS.md`
- Central DataM8 docs: https://github.com/oraylis/datam8/tree/main/docs
- Legacy generator docs location: https://github.com/oraylis/datam8/tree/main/docs/generator

## Local development

### Requirements

- Python 3.12+
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)

### Clone

The repository uses the `datam8-model` git submodule as schema source during model-code generation.

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

### Build wheel

```sh
uv build
```

### Tests

Tests require a DataM8 solution via `--solution-path` or `DATAM8_SOLUTION_PATH`.
In CI, the sample solution (`feature/v2`) is checked out and used.

```sh
uv sync
uv run pytest --solution-path "<path-to-solution.dm8s>"
```

### Linting / checks

```sh
uv tool run ruff check src
uv tool run pyright src
```

### License headers

```sh
uv run python scripts/add_license_headers.py --dry-run
uv run python scripts/add_license_headers.py
```
