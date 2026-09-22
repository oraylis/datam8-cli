# ORAYLIS DataM8 CLI

> [!IMPORTANT]
> The main branch may contain active development, which could contain a broken solution.
> Always use [releases] or their respective [version tags] or commit hashes directly when
> referencing the schema.

[releases]: https://github.com/oraylis/datam8-cli/releases
[version tags]: https://github.com/oraylis/datam8-cli/tags

## Issues

Issues are tracked centrally in the DataM8 repository:

- https://github.com/oraylis/datam8/issues

## Key docs

- Central DataM8 docs: https://github.com/oraylis/datam8/tree/main/docs

## Local development

Check out `justfile`, which contains common commands during development. They can be execute with
[just][just-manual] which is a command runner.

[just-manual]: https://just.systems/man/en/introduction.html

### Requirements

- Python 3.12+
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)
    - setup local venv with `uv sync --all-extras`
    - upgrade dependencies with `uv add -U <dpackage>'
    - use `uv audit` to check for vulnerabilities (experimental at this time)

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

Testing requires a path to a DataM8 solution.
You can pass it via `--solution-path` or environment variable (`DATAM8_SOLUTION_PATH`).
See `tests/README.md` for more details.

```sh
uv sync --all-extras
uv run pytest --solution-path "<path-to-solution.dm8s>"
```

### Linting / checks

`ruff` is used for linting and formatting, for static type checking `ty` is preferred, as it (at
least currently) plays more nicely with a lot of the generic type definitions used. Plus `ty` is a
lot faster than e.g. `pyright`.

```sh
# running the tools directly via uv
uvx ruff check src
uvx ty check src
```

Alternative use the tasks defined in `justfile` to execute them together.

### License headers

```sh
uv run python scripts/add_license_headers.py --dry-run
uv run python scripts/add_license_headers.py
```
