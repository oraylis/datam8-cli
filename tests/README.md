# Testing

The project uses `pytest`.

## Test architecture

The canonical test layout follows the existing `feature/v2` pattern:

- Domain tests live in numbered modules: `test_0xx_<domain>.py`
- Parameter data lives in matching case files: `test_0xx_<domain>_cases.py`
- Cross-test fixtures/helpers live in `tests/conftest.py`

When adding new tests, prefer extending an existing numbered domain and its `*_cases.py`
before creating a new domain module.

## Domain map (what is tested where)

- `test_010_model.py` + `test_010_model_cases.py`: model access, lookup, locator behavior
- `test_020_helper.py` + `test_020_helper_cases.py`: helper/hash/uuid behavior
- `test_030_factory.py` + `test_030_factory_cases.py`: factory/property-value resolution
- `test_040_connector_binding.py` + `test_040_connector_binding_cases.py`: connector binding encode/decode rules
- `test_050_api_connectors.py` + `test_050_api_connectors_cases.py`: connectors API endpoints
- `test_060_api_plugins.py` + `test_060_api_plugins_cases.py`: plugin lifecycle endpoints (install/enable/disable/uninstall)
- `test_070_plugin_loader.py` + `test_070_plugin_loader_cases.py`: plugin loader + vendored dependencies
- `test_080_workspace_io.py` + `test_080_workspace_io_cases.py`: workspace/index/rename scan behavior
- `test_090_cli.py` + `test_090_cli_cases.py`: CLI surface and command behavior
- `test_100_server_integration.py` + `test_100_server_integration_cases.py`: server integration flow (health/auth/generate)

## Shared fixtures and helpers

`tests/conftest.py` is the single place for cross-test setup. Most important fixtures:

- `solution_file_path`: resolves the active `.dm8s` path from `--solution-path` or `DATAM8_SOLUTION_PATH`
- `config`, `model_lazy`, `model`: shared model-centric setup for existing v2-style tests
- `api_client`: context manager fixture to spin up a `TestClient` with optional plugin/solution env wiring
- `fixture_connector_plugins_dir`, `fixture_job_solution_dir`, `temp_plugin_dir`: canonical fixture paths/temp dirs

Do not duplicate env/path/bootstrap logic inside individual test modules. Extend `conftest.py` instead.

## Run all tests

```sh
uv sync
uv run pytest
```

## Solution path

Model-centric and server integration tests require a solution path.

Set it via environment variable:

```sh
export DATAM8_SOLUTION_PATH="/absolute/path/to/ORAYLISDatabricksSample.dm8s"
uv run pytest
```

Or per invocation with `--solution-path`:

```sh
uv run pytest --solution-path="/absolute/path/to/ORAYLISDatabricksSample.dm8s"
```

## CI strict mode

CI uses strict mode for solution-dependent tests:

- `DATAM8_SOLUTION_PATH` must point to a valid `.dm8s` solution
- `DATAM8_REQUIRE_SOLUTION_TESTS=1` turns missing/invalid solution setup into a hard failure

Locally (without strict mode), solution-dependent tests are skipped when no solution path is configured.

## How to add a new test (recommended flow)

1. Find the matching numbered domain (`test_0xx_<domain>.py`).
2. Add input/expected variants to `test_0xx_<domain>_cases.py`.
3. Keep setup minimal in tests; use shared fixtures from `conftest.py`.
4. Add a new domain only if no existing domain fits.
5. Run:
   - `uv run pytest`
   - `uv tool run pyright src`
   - `uv tool run ruff check src`

## Reading skips/failures

- Local runs without solution path: solution-dependent tests are expected to be skipped.
- CI runs with strict mode: missing/invalid solution path is treated as a hard failure.
- Use `uv run pytest -rs` to see skip reasons in detail.
