# Safety Rules

- Never delete or move without inspecting scope first.
- Use `--yes` only after the scope is known.
- Never continue after a non-zero exit code.
- Never edit internal files directly unless the user explicitly requests it and no CLI command exists.
- Prefer `--set` for small patches.
- Use `--json-body` or `--body` only for larger structured request bodies.
- Validate after mutations.
- Do not dump secret values.
- Do not run broad migrations, broad deletes, or secret cleanup without explicit confirmation.
- Do not promise background work for `datam8 serve` or other long-running processes.
- Treat file paths passed to `--body` as payload transport only, not entity identity.
