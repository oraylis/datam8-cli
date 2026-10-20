---
name: datam8-cli
description: Inspect and maintain local DataM8 metadata solutions through the CLI, including nested model edits, source imports and function files. Use for model maintenance rather than changing CLI implementation or editor drafts.
---

# DataM8 model maintenance

Use `datam8` directly on persisted `.dm8s` files; no server is needed.
In a CLI source checkout, run it with `uv run datam8`.
The [CLI contract](../../docs/cli-agent-contract.md) is authoritative. Read only
the relevant section for unfamiliar commands, payloads or output details;
use command-specific `--help` for installed options.

- Bind the intended solution explicitly with `-s PATH` and use command-level
  `--json`. Read stdout as one JSON document; diagnostics go to stderr.
- Discover locators and `sourceFile` with bounded `list --fields ... --limit ...`;
  use `show --fields` or `show --at` for just the required data. Request `schema`
  for the relevant entity type/field when its shape is unknown.
- Use `--file FILE` or `--file -` for mutation JSON to avoid shell quoting.
  Prefer keyed `--at` selectors over list positions; they must match exactly one
  entry. Object updates merge only at the selected level; lists are replaced.
- For Base creation in an existing collection, pass its returned `sourceFile`
  via `--source-file`. Use rename/move for entity identity changes and `functions`
  commands for code/file lifecycle. Data modules belong inside data products.
- Use one `apply --file FILE --json` for related edits. Operations save in order;
  on failure, earlier writes remain. Inspect `results` and `failedIndex`, then
  read the affected state before retrying; do not replay completed creates.
  Express required frontend-only follow-up changes as explicit batch operations.
- For source work, reuse returned handles unchanged; compare is read-only,
  refresh writes (`--yes` in JSON mode). Read the source/function/secret contract
  section only when needed. Pass secret values through stdin, keeping them out
  of command arguments and reports.
- After edits, run `validate --json` and read back the affected fields. Generate
  only when the task calls for generated output, using the intended target.
  Use disposable solutions for experiments and acceptance tests.

Read only one attribute (replace the example solution, locator and key):

```sh
datam8 -s Example.dm8s show modelEntities/Raw/Customer --at '["attributes",{"name":"Id"}]' --json
```

For two related edits, put this in `changes.json`, then run
`datam8 -s Example.dm8s apply --file changes.json --json`:

```json
{"operations":[
  {"op":"update","locator":"modelEntities/Raw/Customer","at":["attributes",{"name":"Id"}],"data":{"description":"Customer identifier"}},
  {"op":"update","locator":"modelEntities/Raw/Customer","data":{"description":"Customer master data"}}
]}
```
