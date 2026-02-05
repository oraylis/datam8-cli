from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class MetadataConnector(Protocol):
    def test_connection(self) -> dict[str, Any]: ...

    def list_schemas(self) -> list[dict[str, Any]]: ...

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]: ...

    def get_table_metadata(self, *, schema: str, table: str) -> dict[str, Any]: ...


class HttpApiConnector(Protocol):
    def request_json_array(self, *, url: str) -> list[Any]: ...


@dataclass(frozen=True)
class ConnectorModule:
    manifest: dict[str, Any]
    create_connector: Callable[[dict[str, Any], dict[str, str]], Any]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    config: dict[str, Any]
    required_secrets: list[str]
    errors: list[dict[str, str]]
