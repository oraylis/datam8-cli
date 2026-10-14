"""Create a new disposable solution; never overwrite an existing directory."""

import json
import shutil
import sys
from pathlib import Path

from plugin import ExamplePlugin


def create_solution(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("Base", "Model/Stage", "Plugins/static_example"):
        (root / folder).mkdir(parents=True, exist_ok=True)

    def write_json(relative: str, value: dict) -> None:
        (root / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    example = Path(__file__).resolve().parent
    for filename in ("plugin.py", "manifest.json"):
        shutil.copyfile(example / filename, root / "Plugins/static_example" / filename)

    write_json(
        "Example.dm8s",
        {
            "schemaVersion": "2.0.0",
            "basePath": "Base",
            "modelPath": "Model",
            "pluginsPath": "Plugins",
            "generatorTargets": [
                {
                    "name": "demo",
                    "isDefault": True,
                    "sourcePath": "Generate",
                    "outputPath": "Output",
                }
            ],
        },
    )
    mappings = ExamplePlugin.get_data_type_mappings()
    types = sorted({mapping.targetType for mapping in mappings})
    write_json(
        "Base/DataTypes.json",
        {
            "type": "dataTypes",
            "dataTypes": [
                {
                    "name": name,
                    "targets": {"demo": name},
                    "hasCharLen": name == "string",
                    "hasPrecision": name == "decimal",
                    "hasScale": name == "decimal",
                }
                for name in types
            ],
        },
    )
    write_json(
        "Base/AttributeTypes.json",
        {
            "type": "attributeTypes",
            "attributeTypes": [
                {
                    "name": "Regular",
                    "displayName": "Regular",
                    "defaultType": "string",
                    "isDefaultProperty": False,
                },
                *[
                    {
                        "name": "Default" + name,
                        "displayName": "Default " + name,
                        "defaultType": name,
                        "isDefaultProperty": True,
                    }
                    for name in types
                ],
            ],
        },
    )
    write_json(
        "Base/Zones.json",
        {
            "type": "zones",
            "zones": [
                {
                    "name": "stage",
                    "displayName": "Stage",
                    "localFolderName": "Stage",
                    "targetName": "stage",
                }
            ],
        },
    )
    write_json(
        "Base/DataSourceTypes.json",
        {
            "type": "dataSourceTypes",
            "dataSourceTypes": [
                {
                    "name": "StaticExample",
                    "pluginId": ExamplePlugin.manifest().id,
                    "authModes": [mode.to_dict() for mode in ExamplePlugin.get_auth_modes()],
                    "connectionProperties": [
                        prop.to_dict() for prop in ExamplePlugin.get_connection_properties()
                    ],
                    "dataTypeMapping": [mapping.to_dict() for mapping in mappings],
                }
            ],
        },
    )
    write_json(
        "Base/DataSources.json",
        {
            "type": "dataSources",
            "dataSources": [
                {
                    "name": "Demo",
                    "type": "StaticExample",
                    "extendedProperties": {"dataset": "customers"},
                }
            ],
        },
    )
    return root / "Example.dm8s"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_solution.py <new-directory>")
    print(create_solution(Path(sys.argv[1]).resolve()))
