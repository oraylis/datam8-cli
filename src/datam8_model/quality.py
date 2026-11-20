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

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class QualityReference(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    entityId: Annotated[int, Field(ge=0)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> QualityReference:
        return QualityReference.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> QualityReference:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        QualityReference
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = QualityReference.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Execution(Enum):
    ENFORCEMENT = "enforcement"
    MONITORING = "monitoring"


class Severity(Enum):
    """
    Defaults to error when omitted.
    """

    ERROR = "error"
    WARNING = "warning"


class OnEmpty(Enum):
    """
    Only with sql. Defaults to evaluate; no_data reports NO_DATA when checked_rows is zero after result validation.
    """

    EVALUATE = "evaluate"
    NO_DATA = "no_data"


class QualityCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    execution: Execution
    expression: Annotated[str, Field(min_length=1, pattern="\\S")]
    """
    Boolean SQL expression passed unchanged to the target engine. Define NULL handling explicitly, for example COALESCE(Amount >= 0, FALSE).
    """
    severity: Severity | None = None
    """
    Defaults to error when omitted.
    """
    description: str | None = None
    sql: Annotated[str | None, Field(min_length=1, pattern="\\S")] = None
    """
    Monitoring-only query returning exactly one row with checked_rows and measured_value. Uses {target} and declared {references.alias} relations.
    """
    onEmpty: OnEmpty | None = None
    """
    Only with sql. Defaults to evaluate; no_data reports NO_DATA when checked_rows is zero after result validation.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> QualityCheck:
        return QualityCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> QualityCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        QualityCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = QualityCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Quality(BaseModel):
    """
    Fixed SQL quality contract. Solutions configure their target runtime and table bindings.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="never",
    )
    maxFailureRatePct: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    """
    Fail after valid target and metric writes when the distinct error-row percentage strictly exceeds this value. Omit to disable the gate.
    """
    checks: Sequence[QualityCheck]
    references: Mapping[str, QualityReference] | None = None
    """
    Named active model entities, used in monitoring SQL as {references.alias}.
    """

    @model_validator(mode="before")
    @classmethod
    def validate_quality_contract(cls, value: Any, info: ValidationInfo) -> Any:
        # Validate raw JSON before Pydantic can coerce numbers or discard nulls.
        from datam8.quality import validate_quality_value

        if isinstance(value, dict) and info.field_name in cls.model_fields:
            # Assignment includes defaults, whereas raw JSON must reject explicit nulls.
            value = {key: item for key, item in value.items() if item is not None}
        return validate_quality_value(value)

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Quality:
        return Quality.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Quality:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Quality
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Quality.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")
