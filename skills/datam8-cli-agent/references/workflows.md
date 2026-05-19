# Workflows

Use `<cli>` for the exact user-provided datam8 command/path and `<solution-arg>` for explicit solution context. Do not run any workflow until both are known.

## Bootstrap
Triggers: first datam8 request without a user-provided CLI command/path or explicit solution context.
Commands: none.
Failure: if `<cli>` is missing, ask for the exact command/path. If solution context is missing, ask for the existing `.dm8s` path or exact new-solution name and target path.
Safety: do not run `datam8 --help`, search for an executable, or infer a solution from the current repository.

## Inspect Entity
Triggers: "show entity", "list entities", "which attributes/sources".
Commands: resolve natural paths first if needed; then use `<cli> list <locator> <solution-arg> --json`, `<cli> show <locator> <solution-arg> --view summary --json`, `<cli> show <locator> <solution-arg> --view attributes --json`, or `<cli> entities sources <locator> <solution-arg> --resolve --json`.
Failure: stop on non-zero exit.
Safety: do not infer from internal files. Use full `<cli> show <locator> <solution-arg> --json` only when a compact view is insufficient.

## Patch Entity
Triggers: "set description", "change display name".
Commands: inspect first, resolve names/natural paths to exactly one locator, confirm the locator and patch, then run `<cli> entities patch <locator> <solution-arg> --set key=value --json`.
Verification: show the result, then run `<cli> validate <solution-arg>`.
Safety: use one input mode only. Never patch a guessed entity.

## Create Entity
Triggers: "create entity", "new entity".
Commands: resolve the target zone if the locator is not fully explicit; inspect `<cli> list modelEntities/<zone-root>/ <solution-arg> --json`; confirm the final target locator; then run `<cli> entities create <locator> <solution-arg> --set description="..." --json` or `--json-body`.
Verification: show the target, then validate.
Safety: do not invent the first model folder; derive it from `zones/<zone>.localFolderName`.

## Delete Entity Safely
Triggers: "delete", "remove".
Commands: resolve the locator, inspect scope with `<cli> list <locator> <solution-arg> --json`, confirm the delete scope, then run `<cli> entities delete <locator> <solution-arg> --yes --json`.
Verification: show should fail after delete, then validate.
Safety: inspect scope before `--yes`.

## Clone Entity
Triggers: "copy", "clone".
Commands: inspect source; resolve target zone and folder hierarchy when target is described naturally; confirm source and target locators; then run `<cli> entities clone <source> <target> <solution-arg> --json`.
Verification: show source and target, then validate.
Safety: target locator must be explicit before mutation.

## Move Entity Safely
Triggers: "move", "rename locator".
Commands: inspect source and target; resolve target zone and folder hierarchy when target is described naturally; confirm source and target locators; then run `<cli> entities move <source> <target> <solution-arg> --json`.
Verification: old locator fails, new locator shows, then validate.
Safety: do not move files directly.

## Import External Source
Triggers: "import table", "create from data source".
Commands: resolve the first segment of natural target paths through `zones/<segment>`; inspect the target hierarchy; optionally inspect metadata with `<cli> sources table-metadata ...`; confirm data source, schema, table, and final target locator; then run `<cli> entities import external <target> <solution-arg> --data-source <data-source> --schema <schema> --table <table> --json`.
Verification: show target, then validate.
Safety: one target entity per invocation. Do not map a natural path directly to `modelEntities/<segment>/...` unless `<segment>` is the resolved `localFolderName` or zone `name`.

## Import Many External Sources
Triggers: "import all tables", "create entities for all source objects".
Commands: resolve the first segment of natural target paths through `zones/<segment>`; inspect hierarchy; confirm the target root when ambiguous; run `<cli> entities import external-all <solution-arg> --data-source <data-source> --target-root <resolved-or-confirmed-target-root> --dry-run --json`; inspect `willCreate`, `skippedExisting`, and `excluded`; confirm scope and conflict handling; then rerun without `--dry-run` using the confirmed options.
Verification: inspect imported locators with compact views, then validate.
Safety: do not invent a default target root. `--target-root` is the final parent folder; do not add a source-schema folder yourself.

## Resolve Zone And Target Hierarchy
Triggers: any create/import/move request that names a natural target path instead of a full locator.
Commands: `<cli> show zones/<segment> <solution-arg> --json`, then `<cli> list modelEntities/<localFolderName-or-zone-name>/ <solution-arg> --json`.
Failure: if the zone does not resolve exactly, inspect available zones with a read-only list/show command and ask for the target zone or full locator.
Safety: this is a blocking preflight for create, move, clone, `entities import external`, and `entities import external-all`. Ask for the folder below the zone root when source context and existing hierarchy do not determine it.

## Import Internal Source
Triggers: "import entity internally", "use this entity as source".
Commands: show source, confirm source and target locators, then run `<cli> entities import internal <target> <solution-arg> --source-locator <source> --json`.
Verification: target sourceLocation equals the source entity id, then validate.
Safety: source must be a model entity.

## Validate And Generate
Triggers: "validate", "check after change", "generate", "run generator".
Commands: `<cli> validate <solution-arg>` after model or solution mutations when validation applies; use `<cli> generate <solution-arg>` only when requested or when the user asks for generation validation.
Failure: summarize stdout/stderr honestly.

## Discover External Source Schemas/Tables/Metadata
Triggers: "which schemas", "which tables", "metadata", "preview", "test connection".
Commands: if unsure, first run `<cli> sources --help`; then use only listed commands such as `list-schemas`, `list-tables`, `table-metadata`, `preview`, or `test-connection`.
Safety: preview is a sample, not full data-quality proof. Do not invent commands from common CLI patterns.

## Manage Function Source
Triggers: "add function", "show function", "delete function source".
Commands: resolve the entity, confirm save/delete mutations, then use `<cli> entities function save/show/delete ...`.
Verification: show the function source or transformations, then validate when the entity changed.
Safety: do not write function files directly in the filesystem during normal workflows.

## Plugins And Secrets
Triggers: "available plugins", "plugin details", "ui schema", "list secrets", "add secret", "remove secret".
Commands: use `<cli> plugins ...` or `<cli> secrets ...` after CLI and solution context are known.
Safety: report secret paths, not values. Confirm destructive secret changes before execution.

## Initialize A New Solution
Triggers: "new blank solution".
Commands: after exact name and target path are provided, run `<cli> init <name> --solution-path <dir-or-file>`.
Safety: do not overwrite existing work or invent a target path.

## Serve API Safely
Triggers: "start api", "serve".
Commands: explain or run `<cli> serve --host 127.0.0.1 --port 0 --token <token> <solution-arg>`.
Safety: do not promise background execution; start a long-running server only when explicitly requested.

## Migrate V1 To V2 Safely
Triggers: "migrate v1".
Commands: confirm v1 input and output dir, then run `<cli> migrate v1-to-v2 --solution-path <v1.dm8s> --output-dir <dir>`.
Safety: output dir may be overwritten/deleted by command behavior.
