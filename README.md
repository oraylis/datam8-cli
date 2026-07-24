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

### Requirements

- Python 3.12+
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)
    - setup local venv with `uv sync --all-extras`

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

```sh
uv tool run ruff check src
uv tool run pyright src
```

### License headers

```sh
uv run python scripts/add_license_headers.py --dry-run
uv run python scripts/add_license_headers.py
```
