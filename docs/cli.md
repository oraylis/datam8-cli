# CLI Usage

The CLI command is `datam8` (or `python -m datam8`). Install the exact selected
backend revision using [README](../README.md). Python `>=3.12` is declared by
`pyproject.toml`; installed desktop supplies its own runtime.

## Discover commands

```sh
datam8 --help
datam8 validate --help
datam8 generate --help
datam8 serve --help
```

CLI flags are version-specific. `--solution` accepts a `.dm8s` path or a directory
with exactly one solution. Quote paths with spaces. Keep exercises in disposable copies.

## Validate and generate

```sh
datam8 validate --solution /path/to/copy/ORAYLISDatabricksSample.dm8s
datam8 generate docs --solution /path/to/copy/ORAYLISDatabricksSample.dm8s
```

The target is a positional name from the descriptor, not a template folder name.
With no explicit target, the solution's default applies. `--payload` selects a
registered payload and can be repeated. `--clean-output` deletes the selected
target directory's contents before generation; keep authored files elsewhere.
The current `--all` flag warns that it is ignored: run targets individually rather
than relying on its help description.

Wait for the process exit code. Success is exit zero; invalid invocation is reported
by Typer and model/loading/generation failures return a nonzero process result.
Do not rely on a universal numeric error-code taxonomy. Inspect the error text and
newly written files; a checked-in output file alone is not proof of success.
Successful generation does not deploy or execute the generated artifacts.

## Serve the editor

```sh
datam8 serve --solution /path/to/copy/ORAYLISDatabricksSample.dm8s --host 127.0.0.1 --port 0 --token replace-with-a-random-token
```

Read the readiness JSON for the actual port. Desktop passes a nonempty token;
browser development requires compatible frontend URL/auth configuration. See
[server](server.md) and [the HTTP contract](backend-contract.md).

## Evidence and boundaries

On 2026-10-01, CLI validate and docs generation ran successfully against a disposable
archive of sample main `68001a2dcaa0b2931ee341f3527b96266a6e46da` with backend
`85683fcaeaf13c4573bee3de9c4668b1ba3ab3b9`. This is CLI evidence, not packaged desktop
or live-source acceptance. See [central compatibility](https://github.com/oraylis/datam8/blob/codex/documentation-v2/docs/compatibility.md)
and [handoff](documentation-handoff.md).
