# AGENTS.md

## Project Overview

Python 3.12+ CLI application (`datam8`) built with Typer, using uv as package manager and hatchling
as build system. Entry point: `datam8.app:app`.

## Structure

- `src/datam8/` — main package
  - `app.py` — Typer app assembly, registers subcommands
  - `__main__.py` — allows `python -m datam8`
  - `config.py` — configuration handling
  - `errors.py` — custom exceptions
  - `factory.py` — object factory
  - `functions.py` — function definitions/logic
  - `generate.py` — code generation orchestration
  - `logging.py` — logging setup
  - `opts.py` — shared CLI options
  - `parser.py` / `parser_v1.py` — input parsing
  - `migration_v1.py` — v1 migration logic
  - `secrets.py` — secrets/keyring integration
  - `source.py` — data source handling
  - `cmd/` — CLI subcommands
  - `model/` — internal data models
    - `model.py` — core model definitions
    - `entity_wrapper.py` — entity wrapper logic
    - `locator.py` — resource locator
  - `plugins/` — plugin system
    - `base.py` — plugin base class
    - `manager.py` — plugin discovery/loading
    - `builtins/` — built-in plugins
  - `solution/` — solution management
  - `utils/` — utilities
    - `cache.py` — caching
    - `hasher.py` — hashing
    - `importer.py` — dynamic imports
  - `api/` — optional FastAPI REST server
    - `app.py` — FastAPI app setup
    - `routes/` — API route definitions
- `src/datam8_model/` — generated models (from JSON schema via datamodel-code-generator)
- `datam8-model/` — git submodule with canonical JSON schema
- `template/` — Jinja2 templates for code generation
- `tests/` — pytest suite
- `pyinstaller/` — standalone binary config

## Commands

See `justfile` for all available commands (executed via `just`). Key recipes: `sync`, `run`,
`build`, `check-format`, `run-tests`.

## Key Patterns

- Subcommand CLI via Typer sub-apps
- Plugin architecture with base class and plugin manager
- Build-time code generation: `hatch_build_datamodel.py` generates Python models from
  `datam8-model/` JSON schema
- Pydantic v2 for data validation
- Jinja2 for template-based output generation
- Polars + PyArrow for data reading/processing in the plugin system

### Error Handling

- `errors.py` defines `Datam8Error` (base) with `code`, `message`, `details`, `hint`, `exit_code`
  and `to_envelope()` → `ErrorEnvelope` (Pydantic model). Subclasses: `Datam8NotFoundError`,
  `Datam8ValidationError`.
- **API**: FastAPI exception handlers in `api/app.py` catch `Datam8Error` → maps exit_code to HTTP
  status → returns JSON `ErrorEnvelope`. Catch-all wraps unknown exceptions as 500. Trace middleware
  assigns UUID per request.
- **CLI**: Errors surface via `typer.Exit(exit_code)` or `sys.exit()`.

### Model Hierarchy

- `Locator` — path-like unique ID (`entityType/folder/entityName`), supports containment, parent
  traversal, rebasing.
- `EntityWrapper[T]` — wraps any entity with `locator`, `source_file`, `entity` (Pydantic model),
  resolved properties, change tracking.
- `EntityRepository[T]` — dict-like container keyed by `Locator` with `get()`, `get_where()`,
  `add()`, `remove()`.
- `Model` — god object holding `EntityRepository` per entity type. Provides `resolve()` (property
  inheritance), `add_entity()`, `delete_entity()`, `save()`.
- **Data flow**: Files → Parser → EntityWrappers in Repositories → `Model.resolve()` → Templates/API
  consume resolved Model.

### Factory (Service Locator)

- `factory.py` holds module-level singletons (`_model`, `_plugin_manager`).
- `get_model()` — lazy-creates Model via `parser.parse_full_solution_async()`.
- `get_plugin_for_data_source()` — resolves DataSource → DataSourceType → Plugin instance.
- Commands and `source.py` use factory as their primary entry point.

### Plugin System

- `Plugin` ABC requires: `manifest()`, `resolve_source_type()`, `parse_source_location()`,
  `get_auth_modes()`, `get_connection_properties()`, `get_data_type_mappings()`.
- Optional capabilities: `test_connection()`, `list_source()`, `get_table_metadata()`,
  `preview_data()` — guarded by `is_capable_of()`.
- `PluginManager` discovers solution plugins from `**/*.json` manifests, loads via `importlib` from
  `entryPoint` field.

### Source Handling

- `source.py` bridges plugins and model: calls `plugin.get_table_metadata()` → transforms
  `SourceField` rows into `Attribute` + `SourceAttributeMapping` → builds `ModelEntity`.
- `compare_entity_with_source()` uses `DeepDiff` for change detection (custom iterable comparison by
  name).

### Code Generation

- `generate.py` uses `@register_payload(template, order=N)` decorator pattern to register payload
  functions.
- **Flow**: load target modules (self-register payloads) → run payloads in parallel per order → each
  returns `IPayload` (data + output_path) → Jinja2 renders → writes output.

### CLI Command Pattern

- Commands accept standard options (`solution_path`, `log_level`, `version`, optionally
  `json_output`).
- Call `common.main_callback()` to set config + logging, then `factory.create_model_or_exit()`.
- Output via `utils.emit_result()` (text/JSON).

### Config

- `config.py` uses module-level globals (not a class). `set_solution(path)` resolves `.dm8s` file.
- `RunMode` enum (CLI/API/TEST) affects error handling behavior.

## Linting & Formatting

Ruff (configured in pyproject.toml): import sorting, pyflakes, pycodestyle, quotes, pyupgrade. Type
checking via `ty`. See `justfile` for exact commands.

## Tests

- **Naming**: Numbered domain modules `test_0XX_<domain>.py` with matching
  `test_0XX_<domain>_cases.py` for parameterized data.
- **Fixtures**: `conftest.py` uses `pytest_cases.fixture`. Key fixtures: `config`, `model`
  (resolved), `model_lazy` (unresolved), `migration`. Solution path via `--solution-path` CLI option
  or `DATAM8_SOLUTION_PATH` env var. Sets `RunMode.TEST`.
- **pytest-cases pattern**: Cases classes named `Cases<Topic>` with `case_<description>` methods.
  Tests consume them via `@parametrize_with_cases("param", cases=CasesFoo, glob="*_pattern")`.
- **Structure**: module-level test functions (not classes), fixtures injected by name.
- **Test data**: `tests/model/` (unit tests), `tests/db/` (database assets),
  `tests/test_040_migration/` (JSON fixtures). Main test data is a real solution provided externally
  via path config.
