# Agent CLI contract

The CLI operates directly on a local solution using the same model operations as
the [HTTP API](backend-contract.md). It does not require a running server. Each
command reads persisted state; editor drafts are not part of that state.

Use `--solution PATH` (`-s`) before or after the command. `DATAM8_SOLUTION_PATH`
and the current directory remain supported. Use `--json` on the selected command.
`init --json` defaults to an empty solution without prompting.

## Output and discovery

Machine commands write one compact UTF-8 JSON document followed by a newline to
stdout. Logs and plugin output go to stderr. Success includes `ok: true`; failures
include `ok: false` and the existing error envelope (`code`, `message`, optional
`details` and `hint`). Exit codes are 0 for success, 2 for input/validation errors,
3 for a missing entity/file/secret, and 1 for other execution failures. Argument
errors are JSON as well. Human-readable commands remain available without `--json`.

| Command | Result |
| --- | --- |
| `solution show [--fields basePath,generatorTargets]` | `item`: selected descriptor fields |
| `list [LOCATOR] [--fields name,description] [--limit N] [--offset N]` | `count`, `offset`, `items`: locator, relative `sourceFile`, ID where present and selected fields |
| `list-by-property PROPERTY_LOCATOR [--model-locator LOCATOR]` | `count`, `offset`, `items`: matching entities |
| `show SELECTOR [--by locator\|id\|name\|relPath] [--at JSON] [--fields FIELD,...]` | `item`: locator, relative `sourceFile`, selected `data` |
| `schema ENTITY_TYPE [--at JSON]` | `item`: existing Pydantic JSON Schema and necessary definitions |
| `validate` | `item.valid` |
| `generate [TARGET] [--payload NAME] [--clean-output]` | `target`, relative `outputPath` |

The default JSON `list` limit is 100; zero requests all items. Results are sorted
by locator, and `count` describes all matches before pagination. An empty list
succeeds. No full entity bodies are included unless requested with `show` or
selected fields. Human `list` output remains unlimited unless a limit is supplied.

## Entity mutations and paths

`create LOCATOR` and `update LOCATOR` accept exactly one of `--data JSON` or
`--file PATH`; `--file -` reads JSON from stdin. `delete LOCATOR`,
`clone LOCATOR NEW_LOCATOR`, `rename LOCATOR NEW_NAME`, and `move SRC DST` use the
existing model semantics. Collection locators use a trailing slash for subtrees.
Mutation receipts contain `changed`, `deleted`, and relative `files`, rather than
returning full entities. All model changes are saved before success is returned.
Model-entity create, clone and import also return a compact `item` with locator
and assigned ID, avoiding a follow-up read just to obtain the ID.

`create --source-file Base/Custom/Types.json` selects an existing same-type Base
collection. The API's [target checks](backend-contract.md#entity-and-function-invariants)
also apply here. Omitting the option preserves default placement. The eight Base
types, model entities and folders are supported. Data modules are nested inside
`dataProducts`, not separate persisted entities.

An optional `--at` JSON array addresses fields inside the entity:

```json
["attributes", {"name": "CustomerId"}, "dataType", "nullable"]
```

Strings address object fields, nonnegative integers address list positions, and
nonempty objects select a list item by exact equality of every supplied key.
Selectors must match exactly one entry. Composite selectors can identify sources,
mappings or relationships without relying on list order.

- `show --at` reads only that value.
- `create --at` appends to a list; an omitted/null terminal list is initialized.
- `update --at` merges object fields at that level. Other values, including lists,
  are replaced. Objects are not recursively merged: select a deeper path when needed.
- `delete --at` removes the selected field or list entry.

The complete owning entity is validated before it is saved. Top-level identity
fields such as entity name, ID, folder path and Property Value property cannot be
changed through update; use rename/move. Adding a nested list entry does not create
an independent file. Entity rename and move retain existing reference/file handling.
Frontend-only folder cascades and attribute rename history are explicit operations,
not inferred by this interface.

## Ordered batches

`apply --file PATH` or `apply --file -` accepts:

```json
{"operations":[
  {"op":"update","locator":"modelEntities/raw/Customer",
   "at":["attributes",{"name":"Id"}],"data":{"description":"Identifier"}},
  {"op":"rename","locator":"modelEntities/raw/Customer","newName":"CustomerV2"}
]}
```

The entire input is structurally validated before operations start. The solution
is loaded once. Each operation uses the individual command's implementation and
is saved in order, so later operations can use earlier changes. Result entries
contain the zero-based `index`, `op` and mutation receipt.

On the first execution failure the process stops with a nonzero exit code and
returns `results` for completed operations, `failedIndex` and `error`. Earlier
saves remain in place. There is no rollback or file transaction; a failing
filesystem operation can itself have partial effects. Unexecuted operations do
not run. Each following CLI invocation reloads persisted state.

Additional operation arguments use these JSON names:

| Operation | Required arguments besides `op` |
| --- | --- |
| `create`, `update` | `locator`, `data`; optional `at`; entity create also accepts `sourceFile` |
| `delete` | `locator`; optional `at` |
| `clone`, `move` | `locator`, `newLocator`; move also accepts `force` |
| `rename` | `locator`, `newName` |
| `sources.import` | `dataSource`, `sourceLocation`, `locator` |
| `sources.refresh` | `locator`; optional `mode` (`complete` or `sources-only`) |
| `functions.create` | `locator`, transformation object in `data`, `sourceCode` |
| `functions.update` | `locator`, `sourceCode`, exactly one of `stepNo` or `name` |
| `functions.delete` | `locator`, exactly one of `stepNo` or `name` |
| `functions.move` | `locator`, `newPath`, exactly one of `stepNo` or `name`; optional `force` |
| `secrets.set` | `path`, `value`; optional `force` |
| `generate` | optional `target`, `payloads`, `cleanOutput`, `lazy` |

## Sources, function files and plugins

All commands below support `--solution` and `--json`:

- `sources capabilities SOURCE`, `sources test-connection SOURCE` and
  `sources list SOURCE [--source-location HANDLE]` support discovery. Pass returned
  `sourceLocation` handles unchanged to `metadata`, `preview` (default 10 rows),
  `import-description`, or `import SOURCE HANDLE LOCATOR`.
- `sources compare LOCATOR [--mode complete|sources-only]` is read-only.
  `sources refresh LOCATOR --yes [--mode ...]` applies changes. JSON refresh requires
  `--yes` and never prompts. Batch refresh is an explicit write operation.
- `functions list [LOCATOR]` omits source code; `functions show LOCATOR --step-no N`
  (or `--name NAME`) reads it. `functions create LOCATOR --step-no N --name NAME
  --source RELATIVE_PATH --file CODE_FILE` creates the transformation and source
  without overwriting existing files. `--code TEXT` is an alternative to `--file`.
  Update uses the same code input and a step/name selector. Move takes a relative
  destination. Delete removes the transformation and only its unshared local file.
  Generic metadata editing does not imply function file creation/deletion.
- `plugins list`, `plugins show ID`, `plugins ui-schema ID`,
  `plugins data-type-mappings ID` and `plugins connection-properties ID` inspect
  connector configuration without creating a connection.
- `secrets check PATH` checks availability. `secrets set PATH --file - [--force]`
  reads the exact secret value from stdin and confirms only the path and stored
  status. Existing interactive secret commands remain available for people.

## Verification

Self-contained CLI regressions are in `tests/test_091_agent_cli.py`. The opt-in
sample check copies a complete, configured solution and does not alter its source:

```sh
uv run python scripts/test_agent_cli_sample.py --solution /path/to/Sample.dm8s --report /tmp/cli-report.json
```

It reads the real AdventureWorks source, imports and edits metadata, exercises
function files, moves and batches, reloads using new CLI processes, and generates
the configured `docs` and `databricks` targets. It never deploys generated output.
This acceptance is separate from CI and is not silently skipped when unavailable.

On 2026-10-20, sample main `4df5d7b` passed initial validation and both generation
targets. Its SQLServer type lacked `pluginId`; real-source acceptance used a
temporary copy with `builtin:SQLServer` and the working AdventureWorks connection
configuration from the local sample feature checkout (`1e1855e`). No credentials
or connection values are stored in reports or this repository.
