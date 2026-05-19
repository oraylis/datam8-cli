# CLI Contract

The public addressing model is the datam8 locator. Internal entity storage files are implementation details and must not be used as the normal mutation interface. Use `<cli>` for the exact user-provided datam8 command/path and `<solution-arg>` for explicit solution context.

## Session Bootstrap
- Do not run or search for a CLI automatically.
- If `<cli>` is missing, stop and ask for the exact command/path to use.
- If solution context is missing, stop and ask for an existing `.dm8s` / `--solution-path ...`, or the exact new-solution name and target path.
- If both values are supplied, do not ask generic onboarding questions.

## Output
- Default output is human-readable.
- Use `--json` for parseable output.
- In `--json` mode, stdout must contain valid JSON only.
- Warnings and logs may use stderr.
- A non-zero exit code means failure. Stop and report it.
- Prefer compact `--view` output for read-only questions. Use full entity output only when the complete entity is needed.

## Command Discovery
- When a command group is unclear, run help through the user-provided CLI, for example `<cli> sources --help`.
- Use only listed subcommands and options.
- Do not invent commands from common CLI patterns.

## Natural Paths And Locators
- Users often describe entities as `<zone>/<folder...>/<entity>`.
- Resolve the first natural path segment with `<cli> show zones/<segment> <solution-arg> --json`.
- Use `localFolderName` as the model root when set; otherwise use the zone `name`.
- Inspect folders with trailing slashes, for example `<cli> list modelEntities/<zone-root>/ <solution-arg> --json`.
- Without the trailing slash, `modelEntities/<zone-root>` is an entity locator, not a folder.
- If the zone, folder, or entity mapping is ambiguous, ask before choosing.

## Mutations
- Mutate model entities only through `<cli> entities ...`.
- Before every create, patch, delete, move, clone, import, or material change, present the resolved locator(s) and intended change; proceed only after user confirmation.
- Deletes and moves require scope inspection before execution.
- Run `<cli> validate <solution-arg>` after mutations.

## Imports
- `<cli> sources import` is not supported.
- External imports use `<cli> entities import external`.
- Broad external imports use `<cli> entities import external-all`; run `--dry-run --json` first and confirm scope before the real import.
- `--target-root` is the final parent folder. Do not append a source-schema folder unless the user explicitly included it in the confirmed target root.
- Do not run imports by mapping a natural path directly to `modelEntities/<segment>/...` unless `<segment>` is the resolved zone `localFolderName` or zone `name`.
- Internal imports use `<cli> entities import internal` and require confirmed source and target locators.

## Compact Entity Views
- `<cli> show <locator> <solution-arg> --view summary --json`
- `<cli> show <locator> <solution-arg> --view attributes --json`
- `<cli> show <locator> <solution-arg> --view sources --json`
- `<cli> show <locator> <solution-arg> --view transformations --json`
- `<cli> entities sources <locator> <solution-arg> --resolve --json`

## Common Command Families
Verify availability with help when command shape is uncertain.
- `list`, `list-by-property`, `show`
- `entities create`, `entities patch`, `entities delete`, `entities clone`, `entities move`, `entities resolve`, `entities sources`
- `entities function show`, `entities function save`, `entities function delete`
- `entities import external`, `entities import external-all`, `entities import internal`
- `sources list-schemas`, `sources list-tables`, `sources table-metadata`, `sources preview`, `sources test-connection`
- `plugins list`, `plugins show`, `plugins ui-schema`
- `secrets list`, `secrets add`, `secrets show`, `secrets unset`, `secrets clean`
- `validate`, `generate`, `init`, `serve`, `migrate v1-to-v2`
