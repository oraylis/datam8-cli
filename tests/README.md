# Testing

The project uses `pytest`.

## Run all tests

```sh
uv sync
uv run pytest
```

## Solution path

Model-centric and server/jobs tests require a solution path.

Set it via environment variable:

```sh
export DATAM8_SOLUTION_PATH="/absolute/path/to/ORAYLISDatabricksSample.dm8s"
uv run pytest
```

Or per invocation with `--solution-path`:

```sh
uv run pytest --solution-path="/absolute/path/to/ORAYLISDatabricksSample.dm8s"
```
