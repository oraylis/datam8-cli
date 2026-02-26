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

from copy import deepcopy

UNKNOWN_PRODUCT = "UnknownProduct"
UNKNOWN_MODULE = "UnknownModule"
UNKNOWN_SOURCE = "unknown"

V2_SCHEMA_VERSION = "2.0.0"

BASE_DIR_NAME = "Base"
MODEL_DIR_NAME = "Model"
GENERATE_DIR_NAME = "Generate"
DIAGRAM_DIR_NAME = "Diagram"
OUTPUT_DIR_NAME = "Output"

ZONE_MODEL_ORDER = ("stage", "core", "curated", "consumer")
ZONE_V1_LABELS = {
    "raw": "Raw",
    "stage": "Stage",
    "core": "Core",
    "curated": "Curated",
    "consumer": "Consumer",
}
ZONE_V2_FOLDERS = {
    "stage": "010-Stage",
    "core": "020-Core",
    "curated": "030-Curated",
    "consumer": "040-Consumer",
}
ZONE_BASE_IDS = {
    "stage": 1000,
    "core": 2000,
    "curated": 3000,
    "consumer": 4000,
}
ZONE_ENTRY_BY_NAME = {
    "raw": {"name": "raw", "targetName": "raw", "displayName": "Raw"},
    "stage": {
        "name": "stage",
        "targetName": "010-Stage",
        "displayName": "Stage",
        "localFolderName": "010-Stage",
    },
    "core": {
        "name": "core",
        "targetName": "020-Core",
        "displayName": "Core",
        "localFolderName": "020-Core",
    },
    "curated": {
        "name": "curated",
        "targetName": "030-Curated",
        "displayName": "Curated",
        "localFolderName": "030-Curated",
    },
    "consumer": {
        "name": "consumer",
        "targetName": "040-Consumer",
        "displayName": "Consumer",
        "localFolderName": "040-Consumer",
    },
}

_DEFAULT_GENERATOR_TARGETS = [
    {
        "name": "default",
        "isDefault": True,
        "sourcePath": "Generate/default",
        "outputPath": "Output/default/generated",
    }
]


def zone_v1_label(zone: str) -> str:
    return ZONE_V1_LABELS[zone]


def zone_v2_folder(zone: str) -> str:
    return ZONE_V2_FOLDERS.get(zone, ZONE_V2_FOLDERS["consumer"])


def default_generator_targets() -> list[dict[str, str | bool]]:
    return deepcopy(_DEFAULT_GENERATOR_TARGETS)
