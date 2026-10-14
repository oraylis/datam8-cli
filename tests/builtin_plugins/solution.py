"""Create disposable real solutions with builtins and matching default attribute types."""

import json
from pathlib import Path


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def create_solution(root: Path, sources: list[tuple]) -> Path:
    solution = root / "Builtin.dm8s"
    write_json(
        solution,
        {
            "schemaVersion": "2.0.0",
            "basePath": "Base",
            "modelPath": "Model",
            "pluginsPath": "Plugins",
            "generatorTargets": [
                {
                    "name": "test",
                    "isDefault": True,
                    "sourcePath": "Generate",
                    "outputPath": "Output",
                }
            ],
        },
    )
    (root / "Model").mkdir(exist_ok=True)
    (root / "Plugins").mkdir(exist_ok=True)
    types = sorted(
        {mapping.targetType for cls, _, _ in sources for mapping in cls.get_data_type_mappings()}
    )
    write_json(
        root / "Base/DataTypes.json",
        {
            "type": "dataTypes",
            "dataTypes": [
                {
                    "name": name,
                    "targets": {"test": name},
                    "hasCharLen": name in {"string", "binary"},
                    "hasPrecision": name == "decimal",
                    "hasScale": name == "decimal",
                }
                for name in types
            ],
        },
    )
    write_json(
        root / "Base/AttributeTypes.json",
        {
            "type": "attributeTypes",
            "attributeTypes": [
                {
                    "name": "Default" + name,
                    "displayName": name,
                    "defaultType": name,
                    "isDefaultProperty": True,
                }
                for name in types
            ],
        },
    )
    write_json(
        root / "Base/Zones.json",
        {
            "type": "zones",
            "zones": [
                {
                    "name": "stage",
                    "displayName": "Stage",
                    "localFolderName": "Stage",
                    "targetName": "stage",
                },
            ],
        },
    )
    write_json(
        root / "Base/DataSourceTypes.json",
        {
            "type": "dataSourceTypes",
            "dataSourceTypes": [
                {
                    "name": cls.__name__,
                    "pluginId": cls.manifest().id,
                    "authModes": [item.to_dict() for item in cls.get_auth_modes()],
                    "connectionProperties": [
                        item.to_dict() for item in cls.get_connection_properties()
                    ],
                    "dataTypeMapping": [item.to_dict() for item in cls.get_data_type_mappings()],
                }
                for cls, _, _ in sources
            ],
        },
    )
    write_json(
        root / "Base/DataSources.json",
        {
            "type": "dataSources",
            "dataSources": [
                {"name": name, "type": cls.__name__, "extendedProperties": properties}
                for cls, name, properties in sources
            ],
        },
    )
    return solution
