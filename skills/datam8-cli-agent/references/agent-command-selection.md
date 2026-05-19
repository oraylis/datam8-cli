# Agent Command Selection

Prefer the smallest parseable locator-based command that answers the user. Compact views are curated CLI output, not raw entity JSON. Use `<cli>` for the exact user-provided datam8 command/path and `<solution-arg>` for explicit solution context.

When unsure about a command group, inspect its current help first with the user-provided CLI, for example `<cli> sources --help`, `<cli> entities import --help`, or `<cli> entities function --help`. Use only commands and options shown by help. Do not invent commands from common CLI patterns.

- Entity summary: `<cli> show <locator> <solution-arg> --view summary --json`
- Entity attributes: `<cli> show <locator> <solution-arg> --view attributes --json`
- Entity sources: `<cli> entities sources <locator> <solution-arg> --resolve --json`
- Entity transformations: `<cli> show <locator> <solution-arg> --view transformations --json`
- Entity id or locator lookup: `<cli> entities resolve <id-or-locator> <solution-arg> --json`
- Zone root lookup for natural paths: resolve the first path segment with `<cli> show zones/<segment> <solution-arg> --json`, then inspect `<cli> list modelEntities/<localFolderName-or-zone-name>/ <solution-arg> --json`. Keep the trailing slash; it marks a folder locator.
- Source discovery when unsure: run `<cli> sources --help`, then choose one of the listed source commands.
- Source tables: `<cli> sources list-tables <data-source> <solution-arg> --schema <schema> --json`
- Source metadata: `<cli> sources table-metadata <data-source> <table> <solution-arg> --schema <schema> --json`
- Single source import into a natural path: resolve `zones/<segment>` first, derive `modelEntities/<localFolderName-or-zone-name>`, inspect hierarchy, confirm the target, then run `<cli> entities import external ... <solution-arg> --json`.
- Bulk source import into a natural path: resolve `zones/<segment>` first, derive `modelEntities/<localFolderName-or-zone-name>`, inspect hierarchy, confirm the target root, then run `<cli> entities import external-all ... <solution-arg> --dry-run --json`; rerun with the user-confirmed conflict/existing-entity options after scope review. `--target-root` is the final parent folder; do not append a source-schema folder yourself.
- Never import to `modelEntities/<natural-zone-segment>` unless that literal folder is the resolved `localFolderName` or zone `name`.
- Function files: use `<cli> entities function save/show/delete`, not direct filesystem edits.

Use full `<cli> show <locator> <solution-arg> --json` only when the complete entity body is required for a mutation or comparison.
