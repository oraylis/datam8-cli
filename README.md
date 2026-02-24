# ORAYLIS DataM8 Generator

`datam8-generator` is the canonical DataM8 v2 backend:

- `datam8` CLI
- `datam8 serve` FastAPI server
- synchronous HTTP execution

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

### CLI arguments (quick reference)

The legacy `dm8gen --action ...` argument model is no longer used.
The current CLI uses command groups under `datam8`.

`datam8 serve`:
- `--token` (required): bearer token for non-health endpoints.
- `--host` (default `127.0.0.1`), `--port` (default `0`).
- `--solution-path` / `--solution` / `-s` (optional).
- `--openapi` (optional), `--log-level` (optional).

`datam8 validate`:
- `--solution-path` / `--solution` / `-s` (required for execution).
- `--log-level` / `-l` (optional).

`datam8 generate`:
- `TARGET` argument (optional, defaults from solution/config).
- `--solution-path` / `--solution` / `-s` (required for execution).
- `--clean-output` / `-c` (optional).
- `--payload` / `-p` (optional, repeatable).
- `--all` (optional), `--lazy` (optional), `--log-level` / `-l` (optional).

For additional command groups (`solution`, `model`, `index`, `plugin`, `secret`, ...),
use `uv run datam8 <group> --help`.

### Build wheel

```sh
uv build
```

### Tests

Testing requires a path to a DataM8 solution.
You can pass it via `--solution-path` or environment variable (`DATAM8_SOLUTION_PATH`).
See `tests/README.md` for details.

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
