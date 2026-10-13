# Standalone build

Build with the local hook directory so that offline ODCS validation includes its schema and license:

```powershell
uv run --with pyinstaller pyinstaller --onedir --name datam8 --paths src --additional-hooks-dir pyinstaller/hooks pyinstaller/datam8_entrypoint.py
```

The new builtins are imported by `datam8.plugins`, so PyInstaller discovers their modules statically.
`hook-datam8.py` collects the pinned ODCS JSON Schema and the upstream license.
The wheel includes these resources through the existing Hatch package configuration.
