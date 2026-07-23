from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from types import SimpleNamespace

import polars as pl
import pytest

import datam8.secrets as secrets_module
from datam8 import plugins
from datam8.api.routes.secrets import SetSecretBody, set_secret
from datam8.plugins.builtins.sql_server import SqlServer
from datam8.plugins.manager import PluginManager
from datam8.secrets import SecretResolver
from datam8_model.data_source import SourceField


def test_builtin_plugins_use_canonical_ids() -> None:
    plugins.init_builtin_plugins()

    assert PluginManager().get_plugin_manifest("builtin:CsvFile").id == "builtin:CsvFile"
    with pytest.raises(Exception, match=r"Plugin `CsvFile` is not registered\."):
        PluginManager().get_plugin_manifest("CsvFile")


@pytest.fixture
def fake_secret_backend(monkeypatch: pytest.MonkeyPatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        secrets_module.keyring,
        "set_password",
        lambda service, username, value: store.__setitem__((service, username), value),
    )
    monkeypatch.setattr(
        secrets_module.keyring,
        "get_password",
        lambda service, username: store.get((service, username)),
    )
    monkeypatch.setattr(
        secrets_module.keyring,
        "delete_password",
        lambda service, username: store.pop((service, username), None),
    )
    monkeypatch.setattr(secrets_module.config, "get_name", lambda: "test-solution")
    monkeypatch.setattr(secrets_module.os, "getlogin", lambda: "tester")
    SecretResolver.reset_singleton()
    yield store
    SecretResolver.reset_singleton()


def test_secret_route_upserts_without_duplicate_registry_entries(fake_secret_backend) -> None:
    path = "datasources/AdventureWorks/password"

    first = asyncio.run(set_secret(SetSecretBody(path=path, value="v1")))
    second = asyncio.run(set_secret(SetSecretBody(path=path, value="v2")))

    assert first.status_code == 204
    assert second.status_code == 204
    assert SecretResolver().get_secret(f"ref://{path}") == "v2"
    assert SecretResolver().get_secret(f"secretRef://{path}") is None
    assert SecretResolver().list_secrets() == [PurePosixPath(path)]


def _make_sql_plugin() -> SqlServer:
    plugin = SqlServer.__new__(SqlServer)
    plugin._data_source = SimpleNamespace(name="AdventureWorks")
    return plugin


def test_sql_metadata_maps_driver_column_names_and_retains_zero_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _make_sql_plugin()
    raw = pl.DataFrame(
        [
            {
                "COLUMN_NAME": "ProductID",
                "ORDINAL_POSITION": 1,
                "DATA_TYPE": "decimal",
                "CHARACTER_MAXIMUM_LENGTH": None,
                "NUMERIC_PRECISION": 10,
                "NUMERIC_SCALE": 0,
                "IS_NULLABLE": "NO",
                "IS_PRIMARY_KEY": 1,
            }
        ]
    )
    monkeypatch.setattr(plugin, "_execute_query", lambda _query: raw)

    metadata = plugin.get_table_metadata("dbo.Product")
    row = metadata.dataframe.to_dicts()[0]
    field = next(metadata.iter_source_fields())

    assert row["name"] == "ProductID"
    assert row["numericScale"] == 0
    assert field == SourceField(
        name="ProductID",
        ordinal=1,
        dataType="decimal",
        numericPrecision=10,
        numbericScale=0,
        isNullable=False,
        isPrimaryKey=True,
    )


def test_sql_metadata_rejects_missing_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _make_sql_plugin()
    monkeypatch.setattr(
        plugin,
        "_execute_query",
        lambda _query: pl.DataFrame([{"COLUMN_NAME": "ProductID"}]),
    )

    with pytest.raises(Exception, match="Invalid source metadata row"):
        plugin.get_table_metadata("dbo.Product")
