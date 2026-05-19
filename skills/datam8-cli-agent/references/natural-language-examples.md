# Natural-Language Examples

These examples use `<cli>` for the user-provided datam8 command/path and `<solution-arg>` for the explicit solution context supplied by the user. Do not replace either with defaults. Placeholder names such as `<folder>`, `<entity>`, `<data-source>`, and `<schema>` are illustrative; never treat them as defaults. Natural paths such as `<zone>/<folder>/<entity>` must be resolved to `modelEntities/...` locators before use.

## 1. "Nutze diese CLI: <cli>. Arbeite mit dieser Solution: <solution.dm8s>."
Classification: supported
Intended behavior: record the provided CLI command/path and solution context for this thread.
Safe next step: run read-only discovery only when needed, for example `<cli> list modelEntities/ <solution-arg> --json`.

## 2. "Zeig mir alle Entities unter <zone>/<folder>/."
Classification: supported
Intended CLI command sequence: `<cli> show zones/<zone> <solution-arg> --json`; derive `modelEntities/<zone-root>`; `<cli> list modelEntities/<zone-root>/<folder>/ <solution-arg> --json`.
Verification step: parse the JSON output and collect matching entity locators.
Expected final answer shape: list the resolved locators; mention if the folder does not exist.

## 3. "Zeig mir die Entity <zone>/<folder>/<entity>."
Classification: supported
Intended CLI command sequence: resolve `zones/<zone>`; inspect the folder if needed; `<cli> show modelEntities/<zone-root>/<folder>/<entity> <solution-arg> --view summary --json`.
Verification step: ensure exactly one entity resolves.
Expected final answer shape: summarize relevant properties from CLI output.

## 4. "Welche Attribute hat <entity> im <zone>/<folder> Ordner?"
Classification: supported
Intended CLI command sequence: resolve `zones/<zone>`; list `modelEntities/<zone-root>/<folder>/`; choose the unique `<entity>` candidate; `<cli> show <resolved-locator> <solution-arg> --view attributes --json`.
Verification step: parse `attributes`.
Expected final answer shape: list attribute names and important metadata.

## 5. "Welche Sources verwendet <zone>/<folder>/<entity>?"
Classification: supported
Intended CLI command sequence: resolve natural path to one locator; `<cli> entities sources <resolved-locator> <solution-arg> --resolve --json`.
Verification step: parse `sources`.
Expected final answer shape: summarize internal and external sources.

## 6. "Vergleiche <source-zone>/<source-folder>/<source-entity> mit <target-zone>/<target-folder>/<target-entity>."
Classification: supported
Intended CLI command sequence: resolve both natural paths through their zones; show both resolved locators with `--json`.
Verification step: parse both entities.
Expected final answer shape: compare attributes, sources, relationships, and transformations.

## 7. "Setze die Beschreibung von <entity> im <zone>/<folder> Ordner auf <description>."
Classification: supported-with-confirmation
Discovery sequence: resolve `zones/<zone>`; list `modelEntities/<zone-root>/<folder>/`; identify the `<entity>` candidate; show compact summary.
Required confirmation: present the resolved locator and exact patch `description=<description>`; run nothing until confirmed.
Execution after confirmation: `<cli> entities patch <resolved-locator> <solution-arg> --set description="<description>" --json`; show result; validate.

## 8. "Ändere <entity>."
Classification: supported-with-clarification
What must be clarified: exact entity and intended field/value.
Safe discovery command: after CLI and solution are known, list likely folders or use locator/search commands available from `<cli> --help`.
Required confirmation: present candidate locators and ask which one to change before patching.

## 9. "Lege <entity> in <zone>/<folder> an."
Classification: supported-with-confirmation
Discovery sequence: resolve `zones/<zone>`; inspect `modelEntities/<zone-root>/`; inspect or ask about `<folder>` if it is missing or ambiguous.
Required confirmation: present final target locator such as `modelEntities/<zone-root>/<folder>/<entity>` and whether this is a blank create or external import.
Execution after confirmation: create/import through `<cli> entities ...`; show result; validate.

## 10. "Importiere <schema>.<table> aus <data-source> nach <zone>/<folder>/<entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve `zones/<zone>`; inspect target folder; optionally inspect table metadata with `<cli> sources table-metadata <data-source> <table> <solution-arg> --schema <schema> --json`.
Required confirmation: present data source, schema, table, and final target locator before import.
Execution after confirmation: `<cli> entities import external <target-locator> <solution-arg> --data-source <data-source> --schema <schema> --table <table> --json`; show summary; validate.

## 11. "Importiere alle Tabellen aus <data-source> nach <zone>/<folder>."
Classification: supported-with-confirmation
Discovery sequence: resolve `zones/<zone>`; inspect `modelEntities/<zone-root>/`; confirm or ask for the final target root.
Dry run: `<cli> entities import external-all <solution-arg> --data-source <data-source> --target-root <confirmed-target-root> --dry-run --json`.
Required confirmation: summarize `willCreate`, `skippedExisting`, and exclusions before the real import.
Execution after confirmation: rerun without `--dry-run` using the user-confirmed conflict/existing-entity options; validate when applicable.

## 12. "Kopiere <source-zone>/<source-folder>/<source-entity> nach <target-zone>/<target-folder>/<target-entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve source and target zones/folders; show source summary; check whether target exists.
Required confirmation: present source and target locators before cloning.
Execution after confirmation: `<cli> entities clone <source-locator> <target-locator> <solution-arg> --json`; show target; validate.

## 13. "Verschiebe <source-zone>/<source-folder>/<entity> nach <target-zone>/<target-folder>/<entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve source and target; show source; check target existence.
Required confirmation: present source and target locators before moving.
Execution after confirmation: `<cli> entities move <source-locator> <target-locator> <solution-arg> --json`; verify old locator fails and new locator shows; validate.

## 14. "Lösche <zone>/<folder>/<entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve natural path; inspect delete scope with `<cli> list <resolved-locator> <solution-arg> --json`.
Required confirmation: present the exact delete scope before using `--yes`.
Execution after confirmation: `<cli> entities delete <resolved-locator> <solution-arg> --yes --json`; verify missing; validate.

## 15. "Welche Schemas gibt es in der Data Source <data-source>?"
Classification: supported
Intended CLI command sequence: `<cli> sources list-schemas <data-source> <solution-arg> --json` when supported by help.
Verification step: inspect returned schemas.
Expected final answer shape: list schemas; do not assume a schema when none was provided.

## 16. "Welche Tabellen gibt es im Schema <schema>?"
Classification: supported-with-clarification
What must be clarified: data source, unless it was already provided in context.
Intended CLI command sequence after clarification: `<cli> sources list-tables <data-source> <solution-arg> --schema <schema> --json`.

## 17. "Zeig mir die Metadaten der Tabelle <schema>.<table>."
Classification: supported-with-clarification
What must be clarified: data source, unless it was already provided in context.
Intended CLI command sequence after clarification: `<cli> sources table-metadata <data-source> <table> <solution-arg> --schema <schema> --json`.

## 18. "Importiere <source-zone>/<source-folder>/<source-entity> intern als <target-zone>/<target-folder>/<target-entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve source and target natural paths; show source; check target.
Required confirmation: present source locator and final target locator.
Execution after confirmation: `<cli> entities import internal <target-locator> <solution-arg> --source-locator <source-locator> --json`; show target; validate.

## 19. "Hinterlege diese Transformationsfunktion auf <zone>/<folder>/<entity>."
Classification: supported-with-confirmation
Discovery sequence: resolve entity; verify the function body path or stdin payload is explicit.
Required confirmation: present locator, source filename, and body source before saving.
Execution after confirmation: `<cli> entities function save <locator> <solution-arg> --source <source-file> --body <path-or-> --json`; show transformations; validate.

## 20. "Prüfe, ob validate erfolgreich ist."
Classification: supported
Intended CLI command sequence: `<cli> validate <solution-arg>`.
Verification step: inspect exit code and output.
Expected final answer shape: report success or concise failure details.

## 21. "Führe generate aus."
Classification: supported
Intended CLI command sequence: `<cli> generate <solution-arg>`.
Verification step: inspect exit code and output.
Expected final answer shape: report success or concise failure details.

## 22. "Welche Entities referenzieren <property-path>?"
Classification: supported
Intended CLI command sequence: `<cli> list-by-property <property-path> <solution-arg> --json`.
Verification step: parse matching entities.
Expected final answer shape: list matching locators.

## 23. "Welche Plugins sind in dieser Solution verfügbar?"
Classification: supported
Intended CLI command sequence: `<cli> plugins list <solution-arg>`.
Verification step: inspect returned plugins.
Expected final answer shape: summarize available plugins.

## 24. "Welche Secrets sind hinterlegt?"
Classification: supported
Intended CLI command sequence: `<cli> secrets list <solution-arg>`.
Verification step: inspect paths only.
Expected final answer shape: list secret paths, not values.

## 25. "Entferne <secret-path>."
Classification: supported-with-confirmation
Discovery sequence: list secrets and confirm the path exists.
Required confirmation: present the exact secret path before unsetting.
Execution after confirmation: `<cli> secrets unset <secret-path> <solution-arg>`.

## 26. "Erstelle eine neue leere datam8 Solution namens <solution-name>."
Classification: supported-with-required-context
What must be provided: exact `<cli>`, solution name, and target path.
Intended CLI command sequence after context: `<cli> init <solution-name> --solution-path <target-dir-or-file>`.
Safety: do not overwrite existing work; stop if target exists or is unclear.

## 27. "Wie starte ich die API für diese Solution?"
Classification: supported
Intended behavior: explain the serve command using the user-provided `<cli>` and `<solution-arg>`.
Example shape: `<cli> serve --host 127.0.0.1 --port 0 --token <token> <solution-arg>`.
Safety: do not start a long-running server unless explicitly requested.

## 28. "Migriere eine v1 Solution nach v2."
Classification: supported-with-confirmation
What must be provided: exact `<cli>`, v1 input path, and output directory.
Required confirmation: present input and output paths because output may be overwritten/deleted by command behavior.
Execution after confirmation: `<cli> migrate v1-to-v2 --solution-path <v1.dm8s> --output-dir <dir>`.

## 29. "Mach die Solution sauber."
Classification: supported-with-clarification
What must be clarified: definition of clean and approved mutations.
Safe discovery command: `<cli> list modelEntities/ <solution-arg> --json`.
Safety: no cleanup mutation without exact scope and confirmation.

## 30. "Ändere einfach die JSON-Datei der Entity direkt."
Classification: unsupported/safe-refusal
Reason: direct internal file editing is not the normal supported mutation interface.
Safer alternative: resolve the entity and use `<cli> entities patch ...` after confirmation.

## 31. "Verschiebe den Entity-File im Dateisystem."
Classification: unsupported/safe-refusal
Reason: file moves bypass locator and model save behavior.
Safer alternative: resolve source and target and use `<cli> entities move ...` after confirmation.
