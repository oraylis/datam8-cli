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
import io
import os
import shutil
import zipfile
from pathlib import Path

import requests

from datam8 import config, model, utils
from datam8_model import solution as s

SAMPLE_SOLUTION_VERSION = "2.0.0-beta.1"
SAMPLE_SOLUTION_REPO_URL = "https://github.com/oraylis/datam8-sample-solution"


DEFAULT_ATTRIBUTE_TYPES_JSON = """{
    "type": "attributeTypes",
    "attributeTypes": [
        {
            "name": "Amt",
            "displayName": "Amount",
            "description": "Amount value having a currency",
            "defaultType": "double",
            "hasUnit": "Currency",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "BirthDate",
            "displayName": "Birth Date of a Person",
            "defaultType": "datetime",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "CreationDate",
            "displayName": "Creation Date",
            "defaultType": "datetime",
            "hasUnit": "NoUnit",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Currency",
            "displayName": "Currency Attribute",
            "defaultType": "string",
            "defaultLength": 3,
            "hasUnit": "NoUnit",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Dsc",
            "displayName": "Description",
            "defaultType": "string",
            "defaultLength": 256,
            "hasUnit": "NoUnit",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "email",
            "displayName": "e-mail Address",
            "defaultType": "string",
            "defaultLength": 256,
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "EMail",
            "displayName": "EMail",
            "defaultType": "string",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Flag",
            "displayName": "Flag",
            "defaultType": "string",
            "defaultLength": 1,
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "ID",
            "displayName": "ID",
            "defaultType": "int",
            "canBeInRelation": true,
            "isDefaultProperty": false
        },
        {
            "name": "Key",
            "displayName": "Key",
            "defaultType": "string",
            "defaultLength": 16,
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Name",
            "displayName": "Name",
            "defaultType": "string",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "PersonalInfo",
            "displayName": "Personal Information",
            "defaultType": "string",
            "defaultLength": 256,
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "SID",
            "displayName": "SID",
            "description": "Identity Type for SCD2 Entities",
            "defaultType": "int",
            "canBeInRelation": true,
            "isDefaultProperty": false
        },
        {
            "name": "Text",
            "displayName": "Text",
            "defaultType": "string",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Unit",
            "displayName": "Unit",
            "description": "Unit for amount quanities",
            "defaultType": "string",
            "defaultLength": 16,
            "hasUnit": "NoUnit",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Val",
            "displayName": "Value",
            "description": "Unit free value",
            "defaultType": "double",
            "hasUnit": "NoUnit",
            "canBeInRelation": false,
            "isDefaultProperty": false
        },
        {
            "name": "Generic String",
            "displayName": "Generic for String",
            "defaultType": "string",
            "canBeInRelation": false,
            "isDefaultProperty": true
        },
        {
            "name": "Generic Datetime",
            "displayName": "Generic for Datetime",
            "defaultType": "datetime",
            "canBeInRelation": false,
            "isDefaultProperty": true
        },
        {
            "name": "Generic Date",
            "displayName": "Generic for Date",
            "defaultType": "date",
            "canBeInRelation": false,
            "isDefaultProperty": true
        },
        {
            "name": "Generic Int",
            "displayName": "Generic for Int",
            "defaultType": "int",
            "canBeInRelation": true,
            "isDefaultProperty": true
        },
        {
            "name": "Generic Double",
            "displayName": "Generic for Double",
            "defaultType": "double",
            "canBeInRelation": false,
            "isDefaultProperty": true
        }
    ]
}
"""

DEFAULT_DATA_TYPES_JSON = """{
  "type": "dataTypes",
  "dataTypes": [
    {
      "name": "string",
      "displayName": "Unicode String (UTF-8) with char length",
      "description": "#",
      "hasCharLen": true,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "string",
        "powerbi": "string"
      }
    },
    {
      "name": "short",
      "displayName": "Integer (16 bit)",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "smallint",
        "powerbi": "int64"
      }
    },
    {
      "name": "int",
      "displayName": "Integer (32 bit)",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "int",
        "powerbi": "int64"
      }
    },
    {
      "name": "long",
      "displayName": "Integer (64 bit)",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "bigint",
        "powerbi": "int64"
      }
    },
    {
      "name": "byte",
      "displayName": "Integer (8 bit)",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "tinyint",
        "powerbi": "int64"
      }
    },
    {
      "name": "double",
      "displayName": "Floating point with double precision",
      "description": "Test 2",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "double",
        "powerbi": "double"
      }
    },
    {
      "name": "bit",
      "displayName": "Bit (1 bit)",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "boolean",
        "powerbi": "boolean"
      }
    },
    {
      "name": "date",
      "displayName": "Date storage yyyy-mm-dd",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "date",
        "powerbi": "date"
      }
    },
    {
      "name": "datetime",
      "displayName": "Date time storage yyyy-mm-dd HH:mm:ss",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "timestamp",
        "powerbi": "timestamp"
      }
    },
    {
      "name": "binary",
      "displayName": "Binary storage",
      "hasCharLen": true,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "binary",
        "powerbi": "binary"
      }
    },
    {
      "name": "uniqueidentifier",
      "displayName": "Unique Identifier",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "string",
        "powerbi": "string"
      }
    },
    {
      "name": "decimal",
      "displayName": "Decimal",
      "hasCharLen": false,
      "hasPrecision": true,
      "hasScale": true,
      "targets": {
        "databricks": "decimal",
        "powerbi": "decimal"
      }
    },
    {
      "name": "money",
      "displayName": "Money",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "decimal(19,4)",
        "powerbi": "decimal"
      }
    },
    {
      "name": "dynstring",
      "displayName": "string without character lenght",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "string",
        "powerbi": "string"
      }
    },
    {
      "name": "dyndecimal",
      "displayName": "decimal with precision and scale",
      "hasCharLen": false,
      "hasPrecision": false,
      "hasScale": false,
      "targets": {
        "databricks": "decimal(19,3)",
        "powerbi": "decimal"
      }
    }
  ]
}
"""

DEFAULT_PROPERTIES_JSON = """{
  "type": "properties",
  "properties": [
    {
      "name": "jobs",
      "displayName": "jobs",
      "schema_": "./jobs.json",
      "scopes": [
        {
          "type": "entity",
          "singleUsage": false,
          "mandatory": false
        }
      ]
    },
    {
      "name": "schedules",
      "displayName": "schedules",
      "schema_": "./schedules.json",
      "scopes": [
        {
          "type": "none"
        }
      ]
    },
    {
      "name": "cluster",
      "displayName": "cluster",
      "schema_": "./cluster.json",
      "scopes": [
        {
          "type": "none"
        }
      ]
    },
    {
      "name": "tags",
      "displayName": "tags",
      "schema_": "./tags.json",
      "scopes": []
    },
    {
      "name": "write_mode",
      "displayName": "write mode",
      "schema_": "./write_mode.json",
      "scopes": [
        {
          "type": "entity",
          "mandatory": true
        }
      ]
    },
    {
      "name": "data_retention",
      "displayName": "data retention",
      "schema_": "./data_retention.json",
      "scopes": [
        {
          "type": "entity",
          "mandatory": false
        }
      ]
    },
    {
      "name": "business_area",
      "displayName": "Business Area",
      "scopes": [
        {
          "type": "folder"
        }
      ]
    },
    {
      "name": "target",
      "displayName": "Target",
      "scopes": [
        {
          "type": "zone"
        }
      ]
    }
  ]
}
"""

DEFAULT_PROPERTY_VALUES_JSON = """{
  "type": "propertyValues",
  "propertyValues": [
    {
      "name": "merge",
      "displayName": "merge",
      "default": true,
      "property": "write_mode"
    },
    {
      "name": "overwrite",
      "displayName": "overwrite",
      "default": false,
      "property": "write_mode"
    },
    {
      "name": "delta",
      "displayName": "Delta",
      "default": false,
      "property": "extract_column"
    },
    {
      "name": "delta",
      "displayName": "Delta",
      "default": false,
      "property": "extract_mode"
    },
    {
      "name": "query",
      "displayName": "Query",
      "default": false,
      "property": "extract_mode"
    },
    {
      "name": "daily",
      "displayName": "Daily",
      "default": true,
      "property": "schedules",
      "cron": "1 0"
    },
    {
      "name": "weekly",
      "displayName": "Weekly",
      "default": false,
      "property": "schedules",
      "cron": "1 0"
    },
    {
      "name": "small",
      "displayName": "S",
      "default": false,
      "property": "cluster",
      "node_type": "Standard_D4ds_v5",
      "num_workers": 4,
      "workload_type": "job"
    },
    {
      "name": "extra_small",
      "displayName": "XY",
      "default": true,
      "property": "cluster",
      "node_type": "Standard_D4ds_v5",
      "num_workers": 2,
      "workload_type": "job"
    },
    {
      "name": "sales_daily",
      "displayName": "Sales (Daily)",
      "default": false,
      "property": "jobs",
      "properties": [
        {
          "property": "schedules",
          "value": "daily"
        },
        {
          "property": "cluster",
          "value": "small"
        }
      ]
    },
    {
      "name": "sales_weekly",
      "displayName": "Sales (Weekly)",
      "default": false,
      "property": "jobs",
      "properties": [
        {
          "property": "schedules",
          "value": "weekly"
        },
        {
          "property": "cluster",
          "value": "extra_small"
        }
      ]
    },
    {
      "name": "sales",
      "displayName": "Sales",
      "property": "business_area"
    },
    {
      "name": "true",
      "displayName": "Has TypeWidening",
      "property": "enable_type_widening"
    },
    {
      "name": "name",
      "displayName": "Name Column Mapping",
      "property": "column_mapping_mode"
    },
    {
      "name": "7_days",
      "displayName": "7 Days Data Retention",
      "property": "data_retention"
    },
    {
      "name": "power-bi",
      "property": "target"
    }
  ]
}
"""


def _write_default_base_entities(base_path: Path) -> None:
    files = {
        "AttributeTypes.json": DEFAULT_ATTRIBUTE_TYPES_JSON,
        "DataTypes.json": DEFAULT_DATA_TYPES_JSON,
        "Properties.json": DEFAULT_PROPERTIES_JSON,
        "PropertyValues.json": DEFAULT_PROPERTY_VALUES_JSON,
    }

    for filename, content in files.items():
        with open(base_path / filename, "x", encoding="utf-8", newline="\n") as _f:
            _f.write(content)


def init_solution(solution_path: Path) -> None:
    solution = s.Solution(
        schemaVersion=config.latest_schema_version(),
        modelPath=Path("model"),
        basePath=Path("base"),
        pluginsPath=Path("plugins"),
        generatorTargets=[
            s.GeneratorTarget(
                name="default",
                sourcePath=Path("generate"),
                outputPath=Path("output"),
                isDefault=True,
            )
        ],
    )

    utils.mkdir(solution_path.parent, recursive=True)

    with open(solution_path, "x", encoding="utf-8", newline="\n") as _f:
        _f.write(solution.model_dump_json(**model.MODEL_DUMP_OPTIONS))

    base_dirs = ["model", "base", "generate", "output", "plugins"]
    for dir_name in base_dirs:
        utils.mkdir(solution_path.parent / dir_name)
        with open(solution_path.parent / dir_name / ".gitkeep", "x", encoding="utf-8") as _f:
            _f.write("")

    _write_default_base_entities(solution_path.parent / "base")


def init_solution_from_sample(solution_path: Path) -> str:
    "Downloads the sample solution and returns the initialed version"
    try:
        response = requests.get(
            f"{SAMPLE_SOLUTION_REPO_URL}/archive/refs/tags/v{SAMPLE_SOLUTION_VERSION}.zip"
        )
    except Exception as err:
        raise utils.create_error(f"Could not download sample solution: {err}")

    if response.status_code != 200:
        raise utils.create_error(f"Could not download sample solution: {response.status_code}")

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        zip_file.extractall(solution_path.parent)

    # the repsitory is in a sub directory, so its needs to be moved one directory up
    for _sub in (solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}").glob(
        "*"
    ):
        shutil.move(_sub, solution_path.parent)

    # cleanup now empty dir
    os.rmdir(solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}/")

    return SAMPLE_SOLUTION_VERSION