# Agent Guide for Template Development

Use this playbook whenever a coding agent (e.g. Codex) works on template logic for DataM8 generators.

## Scope & Key Paths
- Solution descriptor: `datam8-sample-solution/ORAYLISDatabricksSample.dm8s`
- Model metadata JSON: `datam8-sample-solution/Model/**`
- Generator modules: `datam8-sample-solution/Generate/databricks-lake/__modules/payload.py`
- Jinja templates: `datam8-sample-solution/Generate/databricks-lake/*.jinja2`
- Generated artifacts: `datam8-sample-solution/Output/**`

## Daily Workflow
1. Inspect the solution file to confirm `sourcePath` and `outputPath`.
2. Add/update payloads in `__modules/payload.py` using `@register_payload("<template>", order=<int>)`.
3. Craft or adjust the matching Jinja template in the generator folder.
4. Run the generator (cleans output first):
   ```
   uv run dm8gen generate --solution-path 'c:\Users\f.kayser\Projects\ORAYLIS\Automation\Repos\datam8-sample-solution\ORAYLISDatabricksSample.dm8s' -c
   ```
5. Review results under `Output/` to confirm the new payload/template behaved as expected.

## Payload Tips
- `model.modelEntities` gives a `dict[Locator, EntityWrapper]`; each `EntityWrapper.entity` is a `ModelEntity`.
- Use `BasePayload` for simple cases. Subclass `BasePayload` when you need custom `get_data()` or `get_output_path()`.
- Share computed values via `Cache` (`cache.set(..)`, `cache.get(..)`), useful when multiple payloads depend on the same metadata.
- `locator` provides `entityType`, `folders`, and `entityName`; combine them to build output paths.

## Template Tips
- Payload data is exposed as `data` in the template—structure the payload’s `data` object so Jinja can consume it cleanly.
- Keep reusable snippets in helper templates (e.g. `columns.py.jinja2`) and import with Jinja macros.
- Prefer deterministic, side-effect-free templates; output should be regenerated entirely by the CLI.

## Troubleshooting
- Missing template errors: ensure the file exists within the generator’s `sourcePath`.
- Unexpected output: inspect the payload’s data structure, add logging via `logger.debug`, or temporarily write helper values into the template.
- Regeneration always wipes `Output/` when using `-c`; keep custom artifacts outside that directory.

## Remember
- Never mutate unrelated files or reset the repo state—respect existing local changes.
- Document new patterns or caveats back in this file so future sessions start faster.
