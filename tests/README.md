# Testing

The project uses `pytest`.

## Run all tests

```sh
uv sync
uv run pytest
```

## Local solution fixture

Model-centric and server/jobs tests can use the local fixture:

- `tests/fixtures/solutions/minimal-v2/minimal.dm8s`

Set it explicitly when needed:

```sh
export DATAM8_SOLUTION_PATH="tests/fixtures/solutions/minimal-v2/minimal.dm8s"
uv run pytest
```

Or per invocation:

```sh
uv run pytest --solution-path="tests/fixtures/solutions/minimal-v2/minimal.dm8s"
```
