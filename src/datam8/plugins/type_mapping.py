"""Translate source types using the mappings stored in a solution."""

import re
from collections.abc import Sequence

from datam8.errors import Datam8ValidationError
from datam8_model.data_source import SourceDataTypeMapping


def normalize_type(source_type: str) -> str:
    return source_type.strip().lower()


class SourceTypeMapper:
    def __init__(
        self,
        type_mappings: Sequence[SourceDataTypeMapping],
        source_mappings: Sequence[SourceDataTypeMapping] | None = None,
        *,
        data_source: str,
        source_location: str,
    ) -> None:
        self.data_source = data_source
        self.source_location = source_location
        self._source = self._index(source_mappings or [], "Data Source")
        self._type = self._index(type_mappings, "Data Source Type")

    def _index(self, mappings: Sequence[SourceDataTypeMapping], level: str) -> dict[str, str]:
        result = {}
        for mapping in mappings:
            key = normalize_type(mapping.sourceType)
            if not key or not mapping.targetType.strip():
                raise Datam8ValidationError(
                    message=f"Data Source '{self.data_source}': empty {level} type mapping"
                )
            if key in result:
                raise Datam8ValidationError(
                    message=f"Data Source '{self.data_source}': duplicate {level} type mapping for '{mapping.sourceType}'"
                )
            result[key] = mapping.targetType
        return result

    def resolve(self, source_type: str, *, column: str) -> str:
        full = normalize_type(source_type)
        match = re.match(r"[a-z_][a-z0-9_]*", full)
        base = match[0] if match else full
        for mappings in (self._source, self._type):
            if full in mappings:
                return mappings[full]
            if base in mappings:
                return mappings[base]
        raise Datam8ValidationError(
            message=(
                f"Data Source '{self.data_source}', object '{self.source_location}', "
                f"column '{column}': no configured data type mapping for '{source_type}'"
            ),
            details={
                "dataSource": self.data_source,
                "sourceLocation": self.source_location,
                "column": column,
                "sourceType": source_type,
            },
        )
