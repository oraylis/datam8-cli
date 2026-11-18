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
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel

# ruff: disable[UP040]
# HACK: pydantic is not able to probably validate a PEP 695 type alias declaration, only seems to work with
# the legacy TypeAlias from typing
DependencyType: TypeAlias = str
# ruff: enable[UP040]


class Dependency(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]

    @staticmethod
    def from_json_file(path: Path) -> Dependency:
        with open(path, encoding="utf-8") as file:
            model = Dependency.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            file.write(self.model_dump_json(**dump_options))


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
    dependencies: Sequence[Dependency] | None = None
    """
    Additional PyPI requirements needed by native DQX checks, installed on the executing classic tasks.
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
    """
    Omit to supply this binding in both execution modes.
    """

    ENFORCEMENT = "enforcement"
    MONITORING = "monitoring"


class QualityEntityReference(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    entityId: Annotated[int, Field(ge=0)]
    execution: Execution | None = None
    """
    Omit to supply this binding in both execution modes.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> QualityEntityReference:
        return QualityEntityReference.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> QualityEntityReference:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        QualityEntityReference
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = QualityEntityReference.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class QualityTableReference(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    table: Annotated[str, Field(min_length=1)]
    execution: Execution | None = None
    """
    Omit to supply this binding in both execution modes.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> QualityTableReference:
        return QualityTableReference.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> QualityTableReference:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        QualityTableReference
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = QualityTableReference.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Execution2(Enum):
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
    execution: Execution2
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
    execution: Execution2
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
    execution: Execution2
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


class Execution5(Enum):
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
    execution: Execution5
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
    execution: Execution5
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
    execution: Execution5
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


class Execution8(Enum):
    ENFORCEMENT = "enforcement"
    MONITORING = "monitoring"


class Criticality(Enum):
    ERROR = "error"
    WARN = "warn"


class DqxFunctionDefinition(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    function: Annotated[str, Field(min_length=1)]
    arguments: Mapping[str, Any] | None = None
    for_each_column: Sequence[str] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> DqxFunctionDefinition:
        return DqxFunctionDefinition.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> DqxFunctionDefinition:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        DqxFunctionDefinition
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = DqxFunctionDefinition.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class DqxRuleDefinition(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    name: str | None = None
    criticality: Criticality | None = None
    check: Annotated[DqxFunctionDefinition, Field(title="DqxFunctionDefinition")]
    filter: str | None = None
    message_expr: str | None = None
    user_metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> DqxRuleDefinition:
        return DqxRuleDefinition.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> DqxRuleDefinition:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        DqxRuleDefinition
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = DqxRuleDefinition.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class DqxCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: Annotated[str, Field(pattern="^[A-Za-z][A-Za-z0-9_]*$")]
    description: str | None = None
    type: Literal["dqx"]
    execution: Execution8
    definition: Annotated[DqxRuleDefinition, Field(title="DqxRuleDefinition")]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> DqxCheck:
        return DqxCheck.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> DqxCheck:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        DqxCheck
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path, encoding="utf-8") as file:
            model = DqxCheck.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode, encoding="utf-8") as file:
            # write content to disk including a final new line
            file.write(self.model_dump_json(**dump_options) + "\n")


class Quality(BaseModel):
    """
    Entity quality requirements and declarative native DQX definitions. Enforcement retains rejected rows in quarantine.
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
        | DqxCheck
    ]
    referenceDatasets: Mapping[str, QualityEntityReference | QualityTableReference] | None = None
    """
    Named DataFrames supplied to DQX reference checks. All bindings are declared in the model.
    """

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
