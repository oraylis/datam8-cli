---
name: datam8-cli-agent
description: use this skill when operating datam8 solutions through the datam8 cli, especially for locator-based entity inspection, creation, patching, deletion, cloning, moving, external source import, internal source import, validation, and generation. use it for safe, repeatable, agentic datam8 workflows that avoid direct internal file editing and use --json for parseable command output.
---

# Datam8 CLI Agent

Use the `datam8` CLI as the execution backend for datam8 solution work. Address entities by locator, not by internal storage file. Use `--json` whenever command output must be parsed.

Normal workflow:
1. Inspect the current state with `datam8 list ... --json` or `datam8 show ... --json`.
2. Mutate only through CLI commands under `datam8 entities`.
3. Verify with `datam8 show ... --json` or `datam8 list ... --json`.
4. Run `datam8 validate` after mutations.
5. Run `datam8 generate` only when requested or when the user asks for generation validation.

Rules:
- Never edit entity JSON files directly during normal workflows.
- Never use `datam8 sources import`; use `datam8 entities import external`.
- Stop on any non-zero exit code and report the failure clearly.
- Ask a clarifying question before ambiguous or destructive changes.
- Inspect delete and move scope before using `--yes`.
- Do not expose secret values unless the user explicitly asks for one narrow value and the CLI confirmation flow is respected.

Examples:
- Show/list: `datam8 list modelEntities/020-Core --json`; `datam8 show modelEntities/020-Core/Sales/Customer/Customer --json`.
- Create: `datam8 entities create modelEntities/020-Core/NewCustomer --set description="New customer entity" --json`.
- Patch: `datam8 entities patch modelEntities/020-Core/Sales/Customer/Customer --set description="Customer master data" --json`.
- Delete: inspect with `datam8 list <locator> --json`, then `datam8 entities delete <locator> --yes --json`.
- Clone: `datam8 entities clone <source-locator> <target-locator> --json`.
- Move: inspect source and target, then `datam8 entities move <source-locator> <target-locator> --json`.
- Import external: `datam8 entities import external <target-locator> --data-source AdventureWorks --schema Sales --table Customer --json`.
- Import internal: `datam8 entities import internal <target-locator> --source-locator <source-locator> --json`.
- Validate: `datam8 validate`.
- Generate: `datam8 generate`.

References:
- [CLI contract](references/cli-contract.md)
- [Workflows](references/workflows.md)
- [Safety rules](references/safety-rules.md)
- [Natural-language examples](references/natural-language-examples.md)
