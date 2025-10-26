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
- For automation agent guidance, see [`AGENTS.md`](AGENTS.md).

## Local development

### Requirements
- `uv` a project manager for python
  - https://docs.astral.sh/uv/getting-started/installation/
  - manages dependencies including build tools
  - manages different python versions

### Clone repo
We are using a git submodule to pull in the json schema for generating some
classes in the `src/dm8gen/Generated` directory. In order to get a functioning
local copy of this repo you need to also retrieve the submodule which is also
a git repo.

``` sh
# clone a fresh local copy
git clone --recurse-submodules https://github.com/oraylis/datam8-generator.git

# initialize submodule in already existing repo
git submodule update --init --recursive
```

### Execute dm8gen
``` sh
uv run dm8gen <args>

# e.g.
uv run dm8gen --help
```

### Build
``` sh
uv build
```

### Testing
Testing requires that a path to a datam8 solution is provided. Alternatively
can be provided via environment vartiables, see `tests/README.md`.

``` sh
uv run pytest --solution-path <path>
```

### Linting
``` sh
uvx ruff check src

# shorthand for
uv tool run ruff check src
```

## Local execution
When running the generator directly from the repository, e.g. for testing
purposes, it is not possible to directly run the `cli.py` script as it will
break relative imports.

In order to run it, it needs to be recognized by the python interpreter as a
module. To do this run the following from the repository root:

```sh
uv run dm8gen -a refresh_generate # and further options
```

## Arguments

### `--action`, `-a` (Required)
Specifies the action that the tool should perform. The available choices are:

- `validate_index`: Validates the index file based on the provided solution path.
- `generate_template`: Generates templates from the specified source and outputs them to the destination.
- `refresh_generate`: Refreshes the index and regenerates the templates.

### `--path_solution`, `-s` (Required)
Path to the solution file, which should be in JSON format. This file is essential for the tool to validate or generate templates.

### `--path_template_source`, `-src` (Optional)
Specifies the directory or file path where the source templates are located. This argument is required when using the `generate_template` or `refresh_generate` actions.

### `--path_template_destination`, `-dest` (Optional)
Specifies the directory path where the generated templates should be saved. This is also required for the `generate_template` and `refresh_generate` actions.

### `--full_index_scan`, `-i` (Optional)
A boolean flag that determines whether to perform a full index scan or just a refresh. This is primarily used with the `validate_index` action.

### `--path_modules`, `-m` (Optional)
Specifies the directory or file path to the modules that can be registered for use in the template generation process. This is an optional argument, useful for modular template generation.

### `--path_collections`, `-c` (Optional)
Specifies the directory path to Jinja2 template collections, which include blocks and other reusable components. This argument is optional but can be useful for organizing and managing template resources.

### `--log_level`, `-l` (Optional)
Sets the logging level for the tool’s execution. The available levels are:

- `NOTSET`
- `DEBUG`
- `INFO` (default)
- `WARN`
- `ERROR`
- `CRITICAL`

If an invalid log level is provided, the tool defaults to `INFO` and logs a warning.
