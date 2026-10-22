# ORAYLIS DataM8 CLI

DataM8's Python backend opens `.dm8s` solutions, imports and refreshes source metadata,
validates models, generates output, and serves the desktop/web editor over HTTP.

> [!IMPORTANT]
> The main branch may contain active development, which could contain a broken solution.
> Always use [releases] or their respective [version tags] or commit hashes directly when
> installing the backend or referencing its schema.

[releases]: https://github.com/oraylis/datam8-cli/releases
[version tags]: https://github.com/oraylis/datam8-cli/tags

## Install the CLI

To use DataM8, install a prebuilt wheel from [GitHub Releases][releases]. A repository checkout,
Git submodules, and the development tools below are only needed when working on the CLI itself.

### Install with uv (recommended)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Open the [releases page][releases], choose a version compatible with your solution, and download
   the `datam8-<version>-py3-none-any.whl` file under **Assets**. For a v2 solution, select a v2
   release, including a prerelease if necessary.
3. In the directory containing the downloaded wheel, run the following commands. Replace
   `<version>` with the version in the downloaded filename.

```sh
uv tool install --python 3.12 "./datam8-<version>-py3-none-any.whl"
uv tool update-shell
```

uv installs the CLI and its dependencies in an isolated environment and downloads Python 3.12 if
needed. Open a new terminal after updating `PATH`, then verify the installation:

```sh
datam8 --version
datam8 --help
```

See the [uv tools guide](https://docs.astral.sh/uv/guides/tools/) for details.

### Alternative: pipx

If you already use [pipx](https://pipx.pypa.io/stable/installation/) and have Python 3.12 or newer
installed, install the same downloaded wheel with:

```sh
pipx install "./datam8-<version>-py3-none-any.whl"
pipx ensurepath
```

Open a new terminal, then run `datam8 --help`.

### Optional features

The base installation provides the CLI. Install extras when you need these features:

| Extra | Feature |
| --- | --- |
| `api` | REST server via `datam8 serve` |
| `azure` | Azure authentication and storage dependencies |
| `sql` | SQL connectivity via ConnectorX |

For example, install the API extra with uv, or replace an existing base installation:

```sh
uv tool install --force --python 3.12 "./datam8-<version>-py3-none-any.whl[api]"
```

Combine extras as `[api,azure,sql]` when needed. With pipx, use the same wheel path with extras
in `pipx install --force`.

### First steps

For an existing solution:

```sh
datam8 validate --solution "path/to/MySolution.dm8s"
datam8 generate --help
```

With a version that supports blank solution initialization (`datam8 init --help` lists
`--type empty`), create a blank solution in a new directory:

```sh
mkdir MySolution
cd MySolution
datam8 init MySolution --type empty
```

The directory must be empty. The command creates `MySolution.dm8s` and the default base entities.
Use `datam8 <command> --help` to see the options for each command.

### Update or uninstall

To update an installation made with uv, download the wheel from the desired release and install it
with `uv tool install --force --python 3.12 "./datam8-<version>-py3-none-any.whl"`. Include the same
extras you used before. To uninstall, run `uv tool uninstall datam8`.

For pipx installations, use `pipx install --force` with the new wheel, or `pipx uninstall datam8`.

## Issues

Issues are tracked centrally in the DataM8 repository:

- https://github.com/oraylis/datam8/issues

## Key docs

- [Central DataM8 handbook](https://github.com/oraylis/datam8/blob/codex/documentation-v2/docs/index.md)
- [Backend documentation index](docs/index.md)
- [CLI examples and exit/output checks](docs/cli.md)
- [Agent skill for model maintenance](skills/datam8-cli/SKILL.md)
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
