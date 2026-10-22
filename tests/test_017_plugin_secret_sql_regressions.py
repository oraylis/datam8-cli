from __future__ import annotations

import asyncio
import logging
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

    assert PluginManager().get_plugin_manifest("CsvFile").id == "builtin:CsvFile"
    with pytest.raises(Exception, match=r"Plugin `nonexistent` is not registered\."):
        PluginManager().get_plugin_manifest("nonexistent")


@pytest.fixture
def fake_secret_backend(monkeypatch: pytest.MonkeyPatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        secrets_module.keyring,
        "get_keyring",
        lambda: None,
    )
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
    second = asyncio.run(set_secret(SetSecretBody(path=path, value="v2"), force=True))

    assert first.status_code == 204
    assert second.status_code == 204
    assert SecretResolver().get_secret(f"ref://{path}") == "v2"
    assert SecretResolver().get_secret(f"secretRef://{path}") is None
    assert SecretResolver().list_secrets() == [PurePosixPath(path)]


def test_secret_operations_do_not_log_values_or_registry(
    fake_secret_backend, caplog: pytest.LogCaptureFixture
) -> None:
    resolver = SecretResolver()
    path = "datasources/security-regression/password"
    first_value = "initial-password-sentinel"
    updated_value = "updated-password-sentinel"
    registry_marker = "registry-only-sentinel"
    # Register a distinct marker before capture so it only appears in registry
    # contents, rather than the service paths logged by subsequent operations.
    resolver.set_secret(registry_marker, "unused-registry-password")

    with caplog.at_level(logging.DEBUG, logger="datam8.secrets"):
        resolver.set_secret(path, first_value)
        assert resolver.get_secret(path) == first_value
        resolver.set_secret(path, updated_value, force=True)
        assert resolver.get_secret(path) == updated_value
        assert resolver.list_secrets() == [PurePosixPath(registry_marker), PurePosixPath(path)]
        resolver.unset_secret(path)
        assert resolver.get_secret(path) is None
        assert resolver.list_secrets() == [PurePosixPath(registry_marker)]

    assert caplog.records
    for sensitive in (first_value, updated_value, registry_marker):
        assert sensitive not in caplog.text


def _make_sql_plugin() -> SqlServer:
    plugin = SqlServer.__new__(SqlServer)
    plugin._data_source = SimpleNamespace(name="AdventureWorks")  # type: ignore[ty:invalid-assignment]
    return plugin


def test_sql_metadata_maps_driver_column_names_and_retains_zero_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _make_sql_plugin()
    raw = pl.DataFrame(
        [
            {
                "name": "ProductID",
                "ordinal": 1,
                "dataType": "decimal",
                "maxLength": None,
                "numericPrecision": 10,
                "numericScale": 0,
                "isNullable": "NO",
                "isPrimaryKey": 1,
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
        lambda _query: pl.DataFrame([{"name": "ProductID"}]),
    )

    with pytest.raises(Exception):
        plugin.get_table_metadata("dbo.Product")
