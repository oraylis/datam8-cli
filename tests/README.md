# Testing

Use Python 3.12+ and `uv sync --all-extras`. The suite uses pytest with
numbered domain modules and optional `*_cases.py` data providers. Shared model
fixtures are in `conftest.py`; focused tests use `tmp_path` and `monkeypatch`.

## Focused regression tests

These tests provide their own data and need no external solution:

```sh
uv run pytest tests/test_014_source_metadata_port.py tests/test_015_source_mappings.py
```

The source tests cover optional plugin source definitions, legacy fallback, metadata
handles, properties, repeated refresh, invalid targets, internal mappings and HTTP
preview behavior. New tests must not depend on customer solutions or live services.

## Full suite

Model-dependent tests use `config`, `model_lazy` and `model` fixtures. Provide a
**disposable copy** of a compatible solution, because model/CLI tests can write files.
The existing CI uses `oraylis/datam8-sample-solution` at `v2.0.0-beta.3`; new focused
regressions should continue to use self-contained fixtures instead of extending that
dependency.

```sh
uv run pytest tests --solution-path /path/to/copy/ORAYLISDatabricksSample.dm8s
```

Alternatively set `DATAM8_SOLUTION_PATH`. The command-line option takes precedence.
Keep `tests` explicit so pytest loads its option registration before parsing the
custom option. Without a configured solution, model fixtures attempt the current
directory and fail if it has no unique `.dm8s`; they do not automatically skip.

## Domain map

- `010`, `011`, `012`: model access, entities and schema contracts.
- `014`, `015`: metadata and source import/refresh.
- `016`: entity tree operations.
- `017`: plugin, secret and SQL regressions.
- `018`: blank solution initialization.
- `020`, `030`: utilities and property resolution.
- `040_migration`: v1 migration.
- `081`: HTTP lifecycle, readiness and CORS.
- `090`: CLI behavior.
- `model/test_locator.py`: locator unit tests.

Prefer extending the relevant domain. Exercise the public request or operation and
assert the resulting state, including that read-only previews do not mutate the model.
For plugin changes, test default `get_sources() -> None` and authoritative definitions
separately. `[]` is authoritative and is not equivalent to `None`.

## CI checks

```sh
uvx ruff check . --respect-gitignore --exclude datam8-model/
uvx --from ty==0.0.60 ty check src --exit-zero-on-warning
uv build
```

The canonical workflow is `.github/workflows/reusable-lint-build-test.yml`.
The `linting` job runs Ruff and then ty. The full CI test run writes JUnit results;
inspect pytest output and the report, including skip reasons (`pytest -rs`). A green
build alone is not evidence that source behavior or external plugins work.

Builds regenerate `src/datam8_model/` from the pinned submodule. Review generated
changes before retaining them. `just check-format` and `just check-format-tests`
also apply formatting and fixes; they are not read-only checks.
