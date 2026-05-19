# Zone Locator Resolution

When the user describes a model entity as `<zone>/<folder...>/<entity>`, treat the first path segment as a possible zone identifier, not as a literal model folder. Use `<cli>` for the exact user-provided datam8 command/path and `<solution-arg>` for explicit solution context.

Mandatory preflight before mutations:
1. Before any create, move, clone, `entities import external`, or `entities import external-all` that uses a natural target path and does not already provide a full confirmed `modelEntities/...` locator, resolve the first path segment with `<cli> show zones/<segment> <solution-arg> --json`.
2. Read `localFolderName` from the zone result.
3. Build the model root as `modelEntities/<localFolderName>` when `localFolderName` is set, otherwise `modelEntities/<zone.name>`.
4. Run `<cli> list modelEntities/<resolved-zone-root>/ <solution-arg> --json` before choosing any target path below the root.
5. For each folder segment below the zone root, resolve against existing hierarchy before assuming a new folder: check exact matches, case-insensitive matches, and obvious singular/plural, whitespace, hyphen, and underscore variants using read-only `list` commands.
6. Prefer an existing resolved hierarchy and casing when it clearly matches the user request or source context. For example, if the user says `stage/sales/customer` and `modelEntities/010-Stage/Sales/Customer/` exists, use `Sales/Customer` instead of planning a new `sales/customer` folder.
7. If multiple similar folder candidates exist, or if the natural path can map to more than one existing hierarchy, ask the user to choose. Do not pick one silently.
8. Reuse an existing folder only when the user request or source context clearly maps to it. If the request is ambiguous, ask for the folder below the zone root.
9. If `zones/<segment>` does not resolve exactly, inspect available zones with a read-only list/show command and ask the user to choose. Do not guess from common zone names.
10. Do not run `entities import external`, `entities import external-all`, create, move, or clone against a natural path mapped directly to `modelEntities/<segment>/...` unless `<segment>` is the resolved `localFolderName` or zone `name`.

Rules:
- For any new, moved, cloned, imported, or materially changed `modelEntities/...` locator, identify the target zone.
- If the user supplied a full `modelEntities/...` locator, use it, but still understand the first folder as the zone folder.
- If the user supplied a natural path instead of a full locator, resolve the first path segment with `<cli> show zones/<segment> <solution-arg> --json`.
- Use `localFolderName` as the model root folder when it is set; otherwise use the zone `name`.
- The model root is `modelEntities/<localFolderName-or-zone-name>`.
- Never use the natural first segment directly as a model folder unless it is the resolved `localFolderName` or zone `name`.
- Inspect existing hierarchy below the resolved root with `<cli> list modelEntities/<zone-root>/ <solution-arg> --json` before choosing a new target path.
- Resolve natural folder segments below the zone root against existing hierarchy using exact, case-insensitive, and obvious variant checks before creating or importing into a new path.
- Preserve existing folder casing in the final locator when a matching existing hierarchy is found.
- The trailing slash matters for folder locators. `modelEntities/<zone-root>/` means the zone-root folder; `modelEntities/<zone-root>` means an entity named `<zone-root>`.
- Reuse an existing folder hierarchy only when the user request or source context clearly maps to it.
- Ask for the target folder below the zone root when hierarchy is ambiguous.

Example:
- User says "create `<entity>` in `<zone>/<folder>`".
- Resolve `<cli> show zones/<zone> <solution-arg> --json`.
- If the result has `localFolderName: "<zone-root>"`, the target root is `modelEntities/<zone-root>`.
- Then inspect `<cli> list modelEntities/<zone-root>/ <solution-arg> --json`, resolve requested folder segments against existing exact, case-insensitive, and obvious variant matches, and choose or ask for the folder below that root.
- Never run `<cli> entities import external modelEntities/<zone>/...` unless `<zone>` is the resolved `localFolderName` or zone `name`.
