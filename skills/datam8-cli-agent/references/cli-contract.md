# CLI Contract

The public addressing model is the datam8 locator. Internal entity storage files are implementation details and must not be used as the normal mutation interface.

Output:
- Default output is human-readable.
- Use `--json` for parseable output.
- In `--json` mode, stdout must contain valid JSON only.
- Warnings and logs may use stderr.
- A non-zero exit code means failure. Stop and report it.

Imports:
- `datam8 sources import` is not supported.
- External imports use `datam8 entities import external`.
- Internal imports use `datam8 entities import internal`.

Expected command families:
- `datam8 list`
- `datam8 list-by-property`
- `datam8 show`
- `datam8 entities create`
- `datam8 entities patch`
- `datam8 entities delete`
- `datam8 entities clone`
- `datam8 entities move`
- `datam8 entities import external`
- `datam8 entities import internal`
- `datam8 sources list-schemas`
- `datam8 sources list-tables`
- `datam8 sources table-metadata`
- `datam8 sources preview`
- `datam8 sources test-connection`
- `datam8 plugins list`
- `datam8 plugins show`
- `datam8 plugins ui-schema`
- `datam8 secrets list`
- `datam8 secrets add`
- `datam8 secrets show`
- `datam8 secrets unset`
- `datam8 secrets clean`
- `datam8 validate`
- `datam8 generate`
- `datam8 init`
- `datam8 serve`
- `datam8 migrate v1-to-v2`
