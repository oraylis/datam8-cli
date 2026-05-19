---
name: datam8-cli-agent
description: use this skill when operating datam8 solutions through a user-provided datam8 cli command, especially for natural-path and locator-based entity inspection, creation, patching, deletion, cloning, moving, external source import, internal source import, validation, and generation. use it for safe, repeatable, agentic datam8 workflows that avoid direct internal file editing, require explicit solution context, and use --json for parseable command output.
---

# Datam8 CLI Agent

Use the datam8 CLI as the execution backend for datam8 solution work. The user must provide both the exact CLI command/path to run and explicit solution context. Treat internal entity storage files as implementation details; normal work uses CLI commands and datam8 locators.

Command placeholders:
- `<cli>` means the exact user-provided datam8 command/path, for example a binary path, wrapper command, or project runtime invocation.
- `<solution-arg>` means the user-provided existing `.dm8s` / `--solution-path ...` context, or explicit new-solution name and target path.
- Do not search for a CLI, probe `datam8 --help`, or pick a repository-local/default solution when these values are missing.

Bootstrap:
1. If `<cli>` is missing, stop and ask for the exact CLI command/path to use.
2. If solution context is missing, stop and ask for the existing `.dm8s` path or the exact new-solution name and target path.
3. After both are known, run read-only discovery when needed. Use `--json` whenever output must be parsed.
4. When command shape is uncertain, run the relevant help on the user-provided CLI, for example `<cli> sources --help` or `<cli> entities import --help`, and use only listed subcommands/options.

Natural path resolution:
1. Users usually describe entities as `<zone>/<folder...>/<entity>`, not as `modelEntities/...` locators.
2. Treat the first path segment as a possible zone identifier, not as a fixed folder name. Resolve it with `zones/<segment>` and read `localFolderName`.
3. The model root is `modelEntities/<localFolderName>` when set, otherwise `modelEntities/<zone.name>`.
4. Inspect hierarchy with trailing-slash folder locators such as `<cli> list modelEntities/<zone-root>/ <solution-arg> --json`.
5. Resolve each folder segment below the zone root against existing hierarchy before treating it as a new folder: check exact matches, case-insensitive matches, and obvious singular/plural or spacing variants using read-only `list` commands. Prefer an existing resolved casing such as `Sales/Customer` over creating a parallel `sales/customer`.
6. If multiple similar folder candidates exist, or if the user wording does not clearly map to one existing folder, ask the user to choose before any mutation or import.
7. If `zones/<segment>` does not resolve exactly, inspect available zones with a read-only list/show command and ask the user to choose. Do not guess from common zone names.
8. Map natural paths to full locators only when the zone, folders, and entity are clear. If any part is ambiguous, ask.
9. Never use the natural first segment as a literal model folder unless that literal folder is the resolved `localFolderName` or zone `name`.

Normal workflow:
1. Inspect with compact commands such as `<cli> show <locator> <solution-arg> --view summary --json`, `--view attributes`, or `<cli> entities sources <locator> <solution-arg> --resolve --json`.
2. Mutate only through CLI commands under `<cli> entities ...`.
3. For user-supplied names or natural paths, search/list candidates first. Do not guess the target entity.
4. Before every create, patch, delete, move, clone, import, or material change, present the resolved source/target locator and intended mutation; proceed only after the user confirms it.
5. Verify with compact `show --view ... --json` output, using full `show --json` only when the complete entity is needed.
6. Run `<cli> validate <solution-arg>` after model or solution mutations when validation applies.
7. Run `<cli> generate <solution-arg>` only when requested or when the user asks for generation validation.

Rules:
- Never edit entity JSON files directly during normal workflows.
- Treat compact `--view` output as the agent contract. It is curated CLI DTO output, not raw entity storage JSON.
- Stop on any non-zero exit code and report the failure clearly.
- Ask before ambiguous, destructive, or broad changes.
- Inspect delete and move scope before using `--yes`; confirmation is still required before execution.
- Manage transformation function files through `<cli> entities function ...`, not by direct filesystem edits.
- Never use `<cli> sources import`; use `<cli> entities import external`.
- For `entities import external-all`, run `--dry-run --json` first and confirm the scope before running the import.
- Do not expose secret values unless the user explicitly asks for one narrow value and the CLI confirmation flow is respected.

Examples:
- Natural list: user says `<zone>/<folder>/`; resolve `zones/<zone>`, then run `<cli> list modelEntities/<zone-root>/<folder>/ <solution-arg> --json`.
- Natural show: user says `<zone>/<folder>/<entity>`; resolve the zone root, then run `<cli> show modelEntities/<zone-root>/<folder>/<entity> <solution-arg> --view summary --json`.
- Ambiguous patch: user says "Change <entity>"; list/search candidates, ask which resolved locator to change and what field/value, then confirm the exact patch before running it.
- New entity: user says `<zone>/<folder>/<entity>`; resolve `zones/<zone>`, inspect `modelEntities/<zone-root>/`, resolve folder segments against existing hierarchy case-insensitively and with obvious variants, confirm the final target locator if the folder does not clearly exist, then create/import.
- Delete/move/clone/import: inspect source and target scope, present the exact locator(s) and command intent, then mutate only after confirmation.
- Validate: `<cli> validate <solution-arg>`.
- Generate: `<cli> generate <solution-arg>`.

References:
- [CLI contract](references/cli-contract.md)
- [Workflows](references/workflows.md)
- [Safety rules](references/safety-rules.md)
- [Natural-language examples](references/natural-language-examples.md)
- [Agent command selection](references/agent-command-selection.md)
- [Metadata model coverage](references/metadata-model-coverage.md)
- [Zone locator resolution](references/zone-locator-resolution.md)
