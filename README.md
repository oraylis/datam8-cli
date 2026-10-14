# ORAYLIS DataM8 CLI

DataM8's Python backend opens `.dm8s` solutions, imports and refreshes source metadata,
validates models, generates output, and serves the desktop/web editor over HTTP.

> [!IMPORTANT]
> The main branch may contain active development, which could contain a broken solution.
> Always use [releases] or their respective [version tags] or commit hashes directly when
> installing the backend or referencing its schema.

[releases]: https://github.com/oraylis/datam8-cli/releases
[version tags]: https://github.com/oraylis/datam8-cli/tags

## Issues

Issues are tracked centrally in the DataM8 repository:

- https://github.com/oraylis/datam8/issues

## Key docs

- [Central DataM8 handbook](https://github.com/oraylis/datam8/blob/codex/documentation-v2/docs/index.md)
- [Backend documentation index](docs/index.md)
- [CLI examples and exit/output checks](docs/cli.md)
- [Backend HTTP contract, including source import and refresh](docs/backend-contract.md#source-import-and-refresh)
- [Server startup, authentication and CORS](docs/server.md)
- [Plugin development and compatibility](docs/connectors.md)
- [Test setup and commands](tests/README.md)

## Local development

Check out `justfile`, which contains common commands during development. They can be executed with
[just][just-manual] which is a command runner.

[just-manual]: https://just.systems/man/en/introduction.html

### Requirements

- Python 3.12+
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)
    - set up the local environment with `uv sync --all-extras`
    - upgrade dependencies intentionally with `uv add -U <package>`
    - use `uv audit` to check for vulnerabilities (experimental at this time)

### Clone

The repository uses the `datam8-model` git submodule as schema source during model-code generation.

```sh
git clone --recurse-submodules https://github.com/oraylis/datam8-cli.git
cd datam8-cli
uv sync --all-extras
```

### Run CLI

```sh
uv run datam8 --help
uv run datam8 init --help
uv run datam8 serve --help
uv run datam8 validate --help
uv run datam8 generate --help

# or with just

just r --help
just r validate --help
```

`datam8 init` creates a blank solution with the default base entities in an empty directory.

### Build wheel

```sh
uv build
```

### Tests

Model-dependent tests require a path to a disposable DataM8 solution copy.
You can pass it via `--solution-path` or environment variable (`DATAM8_SOLUTION_PATH`).
See `tests/README.md` for more details.

```sh
# Self-contained source regression tests:

uv run pytest tests/test_015_source_mappings.py
# Full suite, including model-dependent tests:

uv run pytest tests --solution-path "<path-to-disposable-solution.dm8s>"
```

### Linting / checks

`ruff` is used for linting and formatting, for static type checking `ty` is preferred, as it (at
least currently) plays more nicely with a lot of the generic type definitions used. Plus `ty` is a
lot faster than e.g. `pyright`.

```sh
# running the tools directly via uv

uvx ruff check . --respect-gitignore --exclude datam8-model/
uvx --from ty==0.0.60 ty check src --exit-zero-on-warning
```

These commands match the CI lint scope and type-checker pin. A failing `linting`
job can come from `ty` even when Ruff passes. The `justfile` formatting tasks also
modify files and use an unpinned type checker.

### License headers

```sh
uv run python scripts/add_license_headers.py --dry-run
uv run python scripts/add_license_headers.py
```
