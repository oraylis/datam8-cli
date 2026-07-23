# Prepared PR Descriptions

## datam8-model

### Title

`Port remaining v2-beta schema capabilities onto main`

### Summary

This PR semantically ports the remaining model capabilities from
`feature/v2-beta` onto a fresh branch from `main`. It intentionally does not
merge the historical beta branch.

### Changes

- Adds `SourceObject.sourceOverride`.
- Adds `SourceField.description`.
- Supports internal integer and external string relationships.
- Adds the `previewData` plugin capability.
- Adds string enums to plugin UI fields.
- Makes `pluginsPath` optional while retaining the `Plugins` default.
- Preserves numeric scale `0`.
- Adds executable schema contract tests.

### Important Decisions

- The beta regression changing numeric scale minimum from `0` to `1` was not
  ported.
- The untyped generated-only `SourceField.relationships` field was not ported.
- Relationship validation uses a JSON Schema condition so code generation
  produces `int | str` without applying string constraints to integers.

### Tests

```text
Schema meta-validation: passed
Schema contract tests: 9 passed
```

### Dependency

The generator PR must reference model commit `fcce955`.

## datam8-generator

### Title

`Port remaining v2-beta APIs and metadata support onto main`

### Summary

This PR ports the remaining useful `feature/v2-beta` behavior onto current
`main` without merging the old branch. Main's generic source architecture,
authentication and safe error envelopes remain canonical.

### Changes

- Regenerates Python models from `datam8-model` commit `fcce955`.
- Adds validated internal and external relationships.
- Adds persistent Base Entity rename support.
- Adds secure Function Source read, write, delete and rename APIs.
- Moves Model Entity function directories with preflight and rollback.
- Adds `previewData` capability enforcement.
- Propagates source descriptions, properties and overrides during import.
- Adds `/schemas` and `/tables` compatibility adapters over `/locations`.
- Fixes existing Main Pyright failures in a separate commit.
- Restores the documented JSON readiness line.
- Replaces the stale backend contract with the implemented endpoint surface.

### Security

- Rejects absolute, drive-qualified, UNC, traversal and empty-segment Function paths.
- Verifies resolved paths remain inside the selected Entity root.
- Rejects resolved symlink escapes.
- Uses temporary files and atomic replacement for Function writes.
- Keeps unexpected exception details out of API responses.

### Tests

```text
ruff src: passed
pyright src: passed, 0 errors
isolated port tests: passed
compatible sample suite: 83 passed, 1 failed, 1 skipped
A/B generated output: 93 vs 93 files, no diff
```

The one suite failure is the absent Sample Property Value
`propertyValues/jobs/sales_weekly`. The skipped test requires Windows symlink
permissions.

The original beta generator required a one-line diagnostic fix to remove
`min_length` from its internal integer Relationship before it could generate.
After that fix, its output and this branch's output were identical.

### Known Follow-ups

- Update the Neon Function bridge from its legacy `relPath` body to the
  canonical `{locator, source, content}` contract.
- Resolve the missing Sample Property Value fixture.
- Keep the `/schemas` and `/tables` routes until consumers use `/locations`.

### Dependency

This PR depends on the `datam8-model` PR and its commit `fcce955`.

### Deliberately Not Ported

- Internal exception leakage.
- Placeholder import endpoints.
- The old SQL-specific plugin interface.
- Manual generated-code drift.
- Untyped `SourceField.relationships`.
- Obsolete beta documentation and hard-coded solution defaults.
