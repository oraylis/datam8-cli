# Workflows

## Inspect Entity
Triggers: "show entity", "list entities", "which attributes/sources".
Commands: `datam8 list <locator> --json` or `datam8 show <locator> --json`.
Verification: parse JSON and answer from the returned entity.
Failure: stop on non-zero exit.
Safety: do not infer from internal files.

## Patch Entity
Triggers: "set description", "change display name".
Commands: inspect first, then `datam8 entities patch <locator> --set key=value --json`.
Verification: `datam8 show <locator> --json`, then `datam8 validate`.
Failure: report the command output.
Safety: use one input mode only.

## Create Entity
Triggers: "create entity", "new entity".
Commands: `datam8 entities create <locator> --set description="..." --json` or `--json-body`.
Verification: `datam8 show <locator> --json`, then `datam8 validate`.
Failure: if locator exists, do not overwrite.
Safety: locator must be explicit.

## Delete Entity Safely
Triggers: "delete", "remove".
Commands: `datam8 list <locator> --json`, then `datam8 entities delete <locator> --yes --json`.
Verification: `datam8 show <locator> --json` should fail, then `datam8 validate`.
Failure: stop on non-zero exit.
Safety: inspect scope before `--yes`.

## Clone Entity
Triggers: "copy", "clone".
Commands: inspect source, then `datam8 entities clone <source> <target> --json`.
Verification: show source and target, then validate.
Failure: if target exists, stop.
Safety: target locator must be explicit.

## Move Entity Safely
Triggers: "move", "rename locator".
Commands: inspect source and target, then `datam8 entities move <source> <target> --json`.
Verification: old locator fails, new locator shows, then validate.
Failure: if target exists or source is missing, stop.
Safety: do not move files directly.

## Import External Source
Triggers: "import table", "create from data source".
Commands: optionally `datam8 sources table-metadata <data-source> <table> --schema-name <schema>`, then `datam8 entities import external <target> --data-source <data-source> --schema <schema> --table <table> --json`.
Verification: show target, then validate.
Failure: missing metadata or existing target stops the workflow.
Safety: one target entity per invocation.

## Import Internal Source
Triggers: "import entity internally", "use this entity as source".
Commands: show source, then `datam8 entities import internal <target> --source-locator <source> --json`.
Verification: target sourceLocation equals source entity id, then validate.
Failure: missing source or existing target stops the workflow.
Safety: source must be a model entity.

## Validate After Mutation
Triggers: "validate", "check after change".
Commands: `datam8 validate`.
Verification: zero exit code.
Failure: summarize stdout/stderr honestly.
Safety: do not keep mutating after validation failure without user direction.

## Generate After Mutation
Triggers: "generate", "run generator".
Commands: `datam8 generate`.
Verification: zero exit code and generated output message.
Failure: summarize errors.
Safety: generation may write output files.

## Discover External Source Schemas/Tables/Metadata
Triggers: "which schemas", "which tables", "metadata", "preview", "test connection".
Commands: `datam8 sources list-schemas <data-source>`, `datam8 sources list-tables <data-source> --schema-name <schema>`, `datam8 sources table-metadata <data-source> <table> --schema-name <schema>`, `datam8 sources preview <data-source> <table> --schema-name <schema>`, `datam8 sources test-connection <data-source>`.
Verification: report only returned schemas, tables, metadata, or preview rows.
Failure: stop and report.
Safety: preview is a sample, not full data-quality proof.

## Inspect Plugins
Triggers: "available plugins", "plugin details", "ui schema".
Commands: `datam8 plugins list`, `datam8 plugins show <plugin-id>`, `datam8 plugins ui-schema <plugin-id>`.
Verification: summarize returned manifest/schema.
Failure: stop and report.
Safety: do not mutate plugins.

## Handle Secrets Safely
Triggers: "list secrets", "add secret", "remove secret".
Commands: `datam8 secrets list`, `datam8 secrets add <path>`, `datam8 secrets unset <path>`.
Verification: report paths, not values.
Failure: stop and report.
Safety: do not dump secret values.

## Initialize A New Solution
Triggers: "new blank solution".
Commands: `datam8 init <name> --solution-path <dir-or-file>`.
Verification: confirm created solution path.
Failure: stop if target exists or directory is not empty.
Safety: do not overwrite existing work.

## Serve API Safely
Triggers: "start api", "serve".
Commands: explain `datam8 serve --host 127.0.0.1 --port 0 --token <token> --solution-path <solution.dm8s>` or run `datam8 serve --help`.
Verification: readiness JSON when explicitly started.
Failure: report startup errors.
Safety: do not promise background execution.

## Migrate V1 To V2 Safely
Triggers: "migrate v1".
Commands: confirm v1 input and output dir, then `datam8 migrate v1-to-v2 --solution-path <v1.dm8s> --output-dir <dir>`.
Verification: inspect output dir.
Failure: stop and report.
Safety: output dir may be overwritten/deleted by command behavior.
