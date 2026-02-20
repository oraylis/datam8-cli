# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_v1_solution_with_unitfree_attribute(tmp_path: Path) -> Path:
    source_root = tmp_path / "legacy_solution"
    (source_root / "Staging").mkdir(parents=True, exist_ok=True)

    _write_json(
        source_root / "Base" / "AttributeTypes.json",
        {
            "items": [
                {
                    "name": "Val",
                    "displayName": "Value",
                    "purpose": "Unit free value",
                    "defaultType": "double",
                    "hasUnit": "UnitFree",
                    "canBeInRelation": False,
                    "isDefaultProperty": False,
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataProducts.json",
        {
            "items": [
                {
                    "name": "Default",
                    "displayName": "Default",
                    "purpose": "",
                    "module": [{"name": "Default", "displayName": "Default", "purpose": ""}],
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataSources.json",
        {
            "items": [
                {
                    "name": "MainSource",
                    "displayName": "MainSource",
                    "purpose": "",
                    "type": "SqlServer",
                    "connectionString": "Server=.;Database=db;",
                    "dataTypeMapping": [{"sourceType": "nvarchar", "targetType": "string"}],
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataTypes.json",
        {
            "items": [
                {
                    "name": "string",
                    "displayName": "String",
                    "purpose": "",
                    "hasCharLen": True,
                    "hasPrecision": False,
                    "hasScale": False,
                    "parquetType": "string",
                    "sqlType": "nvarchar",
                }
            ]
        },
    )
    _write_json(
        source_root / "Legacy.dm8s",
        {
            "basePath": "Base",
            "stagingPath": "Staging",
            "generatePath": "Generate",
            "diagramPath": "Diagram",
        },
    )

    return source_root / "Legacy.dm8s"


def test_migration_route_normalizes_v1_unitfree_attribute_type(tmp_path: Path, api_client) -> None:
    token = "migration-token"
    headers = {"Authorization": f"Bearer {token}"}
    source_solution_path = _create_v1_solution_with_unitfree_attribute(tmp_path)
    target_dir = tmp_path / "migrated"
    target_dir.mkdir(parents=True, exist_ok=True)

    with api_client(token=token) as client:
        response = client.post(
            "/migration/v1-to-v2",
            headers=headers,
            json={
                "sourceSolutionPath": str(source_solution_path),
                "targetDir": str(target_dir),
                "options": {"copyGenerate": False, "copyDiagram": False, "copyOutput": False},
            },
        )
        response.raise_for_status()
        payload = response.json()

        migrated_solution_path = Path(payload["targetSolutionPath"])
        attribute_types_path = migrated_solution_path.parent / "Base" / "AttributeTypes.json"
        attribute_types_payload = json.loads(attribute_types_path.read_text(encoding="utf-8"))

        assert attribute_types_payload["type"] == "attributeTypes"
        assert attribute_types_payload["attributeTypes"][0]["hasUnit"] == "NoUnit"

        open_response = client.get(
            "/solution/full",
            params={"path": str(migrated_solution_path)},
            headers=headers,
        )
        open_response.raise_for_status()


def _create_v1_solution_with_core_features(tmp_path: Path) -> Path:
    source_root = tmp_path / "legacy_solution_core"
    (source_root / "Core").mkdir(parents=True, exist_ok=True)

    _write_json(
        source_root / "Base" / "AttributeTypes.json",
        {
            "items": [
                {
                    "name": "Name",
                    "displayName": "Name",
                    "purpose": "Legacy attribute",
                    "defaultType": "string",
                    "isUnit": "Physical",
                    "canBeInRelation": False,
                    "isDefaultProperty": False,
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataProducts.json",
        {
            "items": [
                {
                    "name": "Sales",
                    "displayName": "Sales",
                    "purpose": "",
                    "module": [{"name": "Customer", "displayName": "Customer", "purpose": ""}],
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataSources.json",
        {
            "items": [
                {
                    "name": "MainSource",
                    "displayName": "MainSource",
                    "purpose": "",
                    "type": "SqlServer",
                    "connectionString": "Server=.;Database=db;",
                    "dataTypeMapping": [{"sourceType": "nvarchar", "targetType": "string"}],
                }
            ]
        },
    )
    _write_json(
        source_root / "Base" / "DataTypes.json",
        {
            "items": [
                {
                    "name": "string",
                    "displayName": "String",
                    "purpose": "",
                    "hasCharLen": True,
                    "hasPrecision": False,
                    "hasScale": False,
                    "parquetType": "string",
                    "sqlType": "nvarchar",
                }
            ]
        },
    )
    _write_json(
        source_root / "Core" / "Customer.json",
        {
            "type": "core",
            "entity": {
                "dataProduct": "Sales",
                "dataModule": "Customer",
                "name": "Customer",
                "displayName": "Customer",
                "purpose": "Entity Purpose",
                "explanation": "Entity Explanation",
                "parameters": [],
                "tags": ["weekly"],
                "attribute": [
                    {
                        "name": "CustomerId",
                        "attributeType": "ID",
                        "dataType": "int",
                        "history": "BK",
                    },
                    {
                        "name": "DisplayName",
                        "attributeType": "Name",
                        "purpose": "Attr Purpose",
                        "explanation": "Attr Explanation",
                        "dataType": "string",
                        "history": "SK",
                    },
                ],
                "relationship": [],
            },
            "function": {
                "source": [
                    {
                        "dm8l": "#",
                        "mapping": [
                            {
                                "name": "DisplayName",
                                "sourceName": "DisplayName",
                                "sourceComputation": "Concat(LastName, ', ', FirstName)",
                            }
                        ],
                    }
                ]
            },
        },
    )
    _write_json(
        source_root / "LegacyCore.dm8s",
        {
            "basePath": "Base",
            "corePath": "Core",
            "generatePath": "Generate",
            "diagramPath": "Diagram",
        },
    )

    return source_root / "LegacyCore.dm8s"


def test_migration_route_maps_sk_bk_and_source_computation(tmp_path: Path, api_client) -> None:
    token = "migration-core-token"
    headers = {"Authorization": f"Bearer {token}"}
    source_solution_path = _create_v1_solution_with_core_features(tmp_path)
    target_dir = tmp_path / "migrated_core"
    target_dir.mkdir(parents=True, exist_ok=True)

    with api_client(token=token) as client:
        response = client.post(
            "/migration/v1-to-v2",
            headers=headers,
            json={
                "sourceSolutionPath": str(source_solution_path),
                "targetDir": str(target_dir),
                "options": {"copyGenerate": False, "copyDiagram": False, "copyOutput": False},
            },
        )
        response.raise_for_status()
        payload = response.json()
        migrated_solution_path = Path(payload["targetSolutionPath"])

        full_response = client.get(
            "/solution/full",
            params={"path": str(migrated_solution_path)},
            headers=headers,
        )
        full_response.raise_for_status()
        full_payload = full_response.json()

        model_entity = next(
            e["content"] for e in full_payload["modelEntities"] if e["content"]["name"] == "Customer"
        )
        assert model_entity["description"] == "Entity Purpose\nEntity Explanation"

        attrs = {a["name"]: a for a in model_entity["attributes"]}
        assert attrs["CustomerId"]["isBusinessKey"] is True
        assert attrs["CustomerId"]["history"] == "SCD0"
        assert attrs["DisplayName"]["history"] == "SCD0"
        assert attrs["DisplayName"]["description"] == "Attr Purpose\nAttr Explanation"
        assert attrs["DisplayName"]["expression"] == "Concat(LastName, ', ', FirstName)"
        assert {"property": "column_type", "value": "SK"} in (attrs["DisplayName"].get("properties") or [])

        properties_base = next(
            b["content"] for b in full_payload["baseEntities"] if b["relPath"] == "Base/Properties.json"
        )
        property_values_base = next(
            b["content"] for b in full_payload["baseEntities"] if b["relPath"] == "Base/PropertyValues.json"
        )
        assert any(p["name"] == "column_type" for p in properties_base["properties"])
        assert any(
            pv["property"] == "column_type" and pv["name"] == "SK"
            for pv in property_values_base["propertyValues"]
        )


def _create_v1_solution_for_folder_and_source_priority(tmp_path: Path) -> Path:
    source_root = tmp_path / "legacy_solution_priority"
    (source_root / "Raw" / "Sales" / "Customer").mkdir(parents=True, exist_ok=True)
    (source_root / "Staging" / "Sales" / "Customer").mkdir(parents=True, exist_ok=True)

    _write_json(source_root / "Base" / "AttributeTypes.json", {"items": [{"name": "ID", "defaultType": "int"}]})
    _write_json(source_root / "Base" / "DataProducts.json", {"items": []})
    _write_json(
        source_root / "Base" / "DataSources.json",
        {"items": [{"name": "AdventureWorks", "type": "SqlServer", "dataTypeMapping": [{"sourceType": "int", "targetType": "int"}]}]},
    )
    _write_json(
        source_root / "Base" / "DataTypes.json",
        {"items": [{"name": "int", "displayName": "Integer", "parquetType": "int", "sqlType": "int"}]},
    )

    _write_json(
        source_root / "Raw" / "Sales" / "Customer" / "Customer_DE.json",
        {
            "type": "raw",
            "entity": {
                "dataProduct": "WrongProduct",
                "dataModule": "WrongModule",
                "name": "Customer_DE",
                "attribute": [{"name": "CustomerID", "type": "int", "nullable": False}],
            },
            "function": {
                "dataSource": "AdventureWorks",
                "sourceLocation": "[SalesLT].[Customer_DE]",
            },
        },
    )
    _write_json(
        source_root / "Staging" / "Sales" / "Customer" / "Customer_DE.json",
        {
            "type": "stage",
            "entity": {
                "dataProduct": "AlsoWrong",
                "dataModule": "StillWrong",
                "name": "Customer_DE",
                "attribute": [{"name": "CustomerID", "type": "int", "nullable": False}],
            },
            "function": {
                "dataSource": "__meta__",
                "sourceLocation": "raw/Sales/Customer/Customer_DE",
                "attributeMapping": [{"source": "CustomerID", "target": "CustomerID"}],
            },
        },
    )

    _write_json(
        source_root / "LegacyPriority.dm8s",
        {
            "basePath": "Base",
            "rawPath": "Raw",
            "stagingPath": "Staging",
            "generatePath": "Generate",
            "diagramPath": "Diagram",
        },
    )
    return source_root / "LegacyPriority.dm8s"


def test_migration_route_prefers_raw_external_source_and_derives_folder_products(tmp_path: Path, api_client) -> None:
    token = "migration-priority-token"
    headers = {"Authorization": f"Bearer {token}"}
    source_solution_path = _create_v1_solution_for_folder_and_source_priority(tmp_path)
    target_dir = tmp_path / "migrated_priority"
    target_dir.mkdir(parents=True, exist_ok=True)

    with api_client(token=token) as client:
        response = client.post(
            "/migration/v1-to-v2",
            headers=headers,
            json={
                "sourceSolutionPath": str(source_solution_path),
                "targetDir": str(target_dir),
                "options": {"copyGenerate": False, "copyDiagram": False, "copyOutput": False},
            },
        )
        response.raise_for_status()
        payload = response.json()
        migrated_solution_path = Path(payload["targetSolutionPath"])

        stage_entity_path = (
            migrated_solution_path.parent
            / "Model"
            / "010-Stage"
            / "Sales"
            / "Customer"
            / "Customer_DE.json"
        )
        stage_entity = json.loads(stage_entity_path.read_text(encoding="utf-8"))
        assert stage_entity["sources"][0]["dataSource"] == "AdventureWorks"
        assert stage_entity["sources"][0]["sourceLocation"] == "[SalesLT].[Customer_DE]"

        zones = json.loads((migrated_solution_path.parent / "Base" / "Zones.json").read_text(encoding="utf-8"))
        zone_names = [z["name"] for z in zones["zones"]]
        assert "raw" in zone_names
        assert "stage" in zone_names
        assert "consumer" not in zone_names
        assert "core" not in zone_names
        assert "curated" not in zone_names

        data_products = json.loads((migrated_solution_path.parent / "Base" / "DataProducts.json").read_text(encoding="utf-8"))
        sales = next((dp for dp in data_products["dataProducts"] if dp["name"] == "Sales"), None)
        assert sales is not None
        assert any(dm["name"] == "Customer" for dm in sales["dataModules"])
