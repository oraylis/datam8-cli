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

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QualitySettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    maxFailureRatePct: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    """
    Stop dependent processing after writing valid rows when the percentage of distinct error rows exceeds this value. Omit to disable threshold failure.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> QualitySettings:
        return QualitySettings.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> QualitySettings:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        QualitySettings
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = QualitySettings.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Execution(Enum):
    ENFORCEMENT = "enforcement"
    MONITORING = "monitoring"


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


class NotNullCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["not_null"]
    execution: Execution
    severity: Severity
    attribute: Annotated[str, Field(min_length=1)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> NotNullCheck:
        return NotNullCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> NotNullCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        NotNullCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = NotNullCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    min: float
    max: float | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters:
        return Parameters.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    min: float | None = None
    max: float

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters1:
        return Parameters1.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters1:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters1
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters1.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class RangeCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["range"]
    execution: Execution
    severity: Severity
    attribute: Annotated[str, Field(min_length=1)]
    parameters: Parameters | Parameters1

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> RangeCheck:
        return RangeCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> RangeCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        RangeCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = RangeCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    expression: Annotated[str, Field(min_length=1)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters2:
        return Parameters2.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters2:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters2
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters2.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class SqlExpressionCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["sql_expression"]
    execution: Execution
    severity: Severity
    parameters: Parameters2

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> SqlExpressionCheck:
        return SqlExpressionCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> SqlExpressionCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        SqlExpressionCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = SqlExpressionCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Execution3(Enum):
    MONITORING = "monitoring"


class Parameters3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    minCompleteness: Annotated[float, Field(ge=0.0, le=1.0)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters3:
        return Parameters3.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters3:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters3
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters3.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class CompletenessCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["completeness"]
    execution: Execution3
    severity: Severity
    attribute: Annotated[str, Field(min_length=1)]
    parameters: Parameters3

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> CompletenessCheck:
        return CompletenessCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> CompletenessCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        CompletenessCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = CompletenessCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    maxAgeSeconds: Annotated[int, Field(ge=0)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters4:
        return Parameters4.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters4:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters4
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters4.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class FreshnessCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["freshness"]
    execution: Execution3
    severity: Severity
    attribute: Annotated[str, Field(min_length=1)]
    parameters: Parameters4

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> FreshnessCheck:
        return FreshnessCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> FreshnessCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        FreshnessCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = FreshnessCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    minCount: Annotated[int, Field(ge=0)]
    maxCount: Annotated[int | None, Field(ge=0)] = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters5:
        return Parameters5.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters5:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters5
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters5.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Parameters6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    minCount: Annotated[int | None, Field(ge=0)] = None
    maxCount: Annotated[int, Field(ge=0)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> Parameters6:
        return Parameters6.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Parameters6:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Parameters6
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = Parameters6.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class RowCountCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["row_count"]
    execution: Execution3
    severity: Severity
    parameters: Parameters5 | Parameters6

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> RowCountCheck:
        return RowCountCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> RowCountCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        RowCountCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = RowCountCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Quality(BaseModel):
    """
    Platform-neutral entity quality requirements. Enforcement always retains rejected rows in quarantine.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    settings: Annotated[QualitySettings | None, Field(title="QualitySettings")] = None
    checks: Sequence[
        NotNullCheck
        | RangeCheck
        | SqlExpressionCheck
        | CompletenessCheck
        | FreshnessCheck
        | RowCountCheck
    ]

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
