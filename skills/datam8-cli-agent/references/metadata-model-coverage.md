# Metadata Model Coverage

Current CLI coverage:
- Treat this file as guidance, not a frozen contract. When capability boundaries matter, check the current `<cli> ... --help` output first.
- All top-level metadata entity collections are technically addressable by locator through `<cli> entities create/show/patch/delete`: `properties`, `propertyValues`, `zones`, `dataTypes`, `dataSourceTypes`, `dataProducts`, `dataModules`, `attributeTypes`, `dataSources`, `folders`, and `modelEntities`.
- Zone entities define the first model folder through `localFolderName`. Natural path prefixes must be resolved through `zones/<segment>` before creating, moving, cloning, or importing model entities.
- Model entity import helpers cover common external and internal source creation.
- Function source files are managed through `<cli> entities function ...`.

Known gaps:
- Do not patch `name` as a rename mechanism. Renames must use `<cli> entities move`; patching `name` can desynchronize locator identity from entity identity.
- Solution-level metadata in the `.dm8s` file is not yet covered by locator-based mutation commands.
- Nested model entity members are only patchable by replacing whole top-level arrays or fields. There are no granular CLI commands yet for attributes, sources, relationships, transformations, parameters, or property references.
- `entities function save` only manages the function source file. The corresponding `transformations[]` metadata still has to be maintained separately.
- Folder creation currently requires the caller to provide an id; the CLI does not allocate folder ids.

Recommended next CLI work:
- Block or explicitly reject `entities patch <locator> --set name=...`.
- Add granular locator-based subcommands for model entity attributes, sources, transformations, relationships, and properties.
- Add a solution-level command family for safe `.dm8s` metadata changes.
- Couple function source creation with optional transformation metadata creation or update.
