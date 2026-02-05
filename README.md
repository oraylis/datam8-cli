# ORAYLIS DataM8 Generator
This repository contains the generator used by DataM8 to generate the solution
output. It can also be used as a standalone cli in ci/cd processes.

## Issues
Issues are centrally maintained in a different repository

https://github.com/oraylis/datam8

## Documentation
The DataM8 documentation is also centrally stored at the following place

https://github.com/oraylis/datam8/tree/main/docs

The specific Generator documentation is located [here](https://github.com/oraylis/datam8/tree/main/docs/generator).

## Local development

### Requirements
- `uv` a project manager for python
  - https://docs.astral.sh/uv/getting-started/installation/
  - manages dependencies including build tools
  - manages different python versions

### Clone repo
We are using a git submodule to pull in the JSON schemas for generating
Pydantic models under `src/datam8_model`. In order to get a functioning
local copy of this repo you need to also retrieve the submodule which is also
a git repo.

``` sh
# clone a fresh local copy
git clone --recurse-submodules https://github.com/oraylis/datam8-generator.git

# initialize submodule in already existing repo
git submodule update --init --recursive
```

### Execute `datam8`
``` sh
uv run datam8 <command> [args]

# e.g.
uv run datam8 --help
uv run datam8 generate --help
uv run datam8 serve --help
```

### Build
``` sh
uv build
```

### Testing
Testing can run against the included fixtures; see `tests/test_900_server_jobs.py` for the server+jobs contract.

``` sh
uv run pytest
```

### Linting
``` sh
uvx ruff check src

# shorthand for
uv tool run ruff check src
```

## Local execution
`datam8` is a Typer-based CLI. Use `datam8 generate` for template generation and `datam8 serve` to start the FastAPI backend used by DataM8 Neon.

See:
- `docs/server.md` for the `datam8 serve` readiness/auth/CORS protocol.
- `docs/jobs.md` for the Job + SSE contract.
- `docs/migration-neon-to-generator.md` for the original Neon→Generator mapping notes.

## Building the `datam8` binary (PyInstaller)
The Electron app ships a frozen `datam8` binary (no Python required at runtime). Build output is written to:

`dist/bin/<platform>/datam8(.exe)`

Local build (requires Python 3.12+ and PyInstaller build deps):
```sh
uv run python scripts/build_binaries.py
```

Notes:
- On Windows, rebuild may fail if a running `datam8.exe` is locked; terminate it and retry.
- The build excludes `pkg_resources` to avoid the deprecated API warning at runtime.

## Troubleshooting
See `docs/server.md` (CORS/auth), and `docs/jobs.md` (Jobs/SSE contract). For Windows build/runtime pitfalls (locked exe), see `docs/jobs.md` and the Neon docs.
