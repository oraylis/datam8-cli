from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import polars as pl
import pytest
from typer.testing import CliRunner

import datam8.secrets as secrets_module
from datam8 import plugins
from datam8.api.routes.secrets import SetSecretBody, set_secret
from datam8.app import app
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


@pytest.fixture
def secret_cli_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    solution = tmp_path / "Test.dm8s"
    solution.touch()
    monkeypatch.setattr(secrets_module.config, "solution_path", solution, raising=False)
    monkeypatch.setattr(secrets_module.config, "solution_folder_path", tmp_path, raising=False)
    return ["-s", str(solution), "secrets"]


@pytest.mark.parametrize("prefix", ["", "ref://"])
def test_secret_cli_set_and_check_resolve_the_same_path(
    prefix: str, secret_cli_args: list[str], fake_secret_backend
) -> None:
    path = "datasources/SecretCliFixture/bearer_token"
    token = "secret-cli-test-token"
    runner = CliRunner()

    stored = runner.invoke(
        app, [*secret_cli_args, "set", prefix + path, "--file", "-", "--json"], input=token
    )
    assert stored.exit_code == 0, stored.output
    assert json.loads(stored.stdout) == {"ok": True, "path": path, "stored": True}

    for argument in (path, f"ref://{path}"):
        checked = runner.invoke(app, [*secret_cli_args, "check", argument, "--json"])
        assert checked.exit_code == 0, checked.output
        assert json.loads(checked.stdout) == {
            "ok": True,
            "item": {"path": path, "available": True},
        }

    resolver = SecretResolver()
    assert resolver.get_secret(f"ref://{path}") == token
    assert resolver.list_secrets() == [PurePosixPath(path)]


def test_secret_cli_add_and_unset_keep_legacy_key_addressable(
    secret_cli_args: list[str], fake_secret_backend
) -> None:
    path = "datasources/SecretCliFixture/bearer_token"
    legacy_path = f"ref:/{path}"
    resolver = SecretResolver()
    resolver.set_secret(legacy_path, "legacy-secret")
    runner = CliRunner()

    added = runner.invoke(app, [*secret_cli_args, "add", f"ref://{path}"], input="new-secret\n")
    assert added.exit_code == 0, added.output
    assert resolver.get_secret(path) == "new-secret"
    assert resolver.get_secret(legacy_path) == "legacy-secret"

    removed_legacy = runner.invoke(app, [*secret_cli_args, "unset", legacy_path])
    assert removed_legacy.exit_code == 0, removed_legacy.output
    assert resolver.get_secret(f"ref://{path}") == "new-secret"
    assert resolver.list_secrets() == [PurePosixPath(path)]

    removed = runner.invoke(app, [*secret_cli_args, "unset", f"ref://{path}"])
    assert removed.exit_code == 0, removed.output
    assert resolver.get_secret(path) is None
    assert resolver.list_secrets() == []


def test_secret_route_upserts_without_duplicate_registry_entries(fake_secret_backend) -> None:
    path = "datasources/AdventureWorks/password"

    first = asyncio.run(set_secret(SetSecretBody(path=path, value="v1")))
    second = asyncio.run(set_secret(SetSecretBody(path=path, value="v2"), force=True))

    assert first.status_code == 204
    assert second.status_code == 204
    assert SecretResolver().get_secret(f"ref://{path}") == "v2"
    assert SecretResolver().get_secret(f"secretRef://{path}") is None
    assert SecretResolver().list_secrets() == [PurePosixPath(path)]


def test_secret_operations_do_not_log_values_or_registry_metadata(
    fake_secret_backend, caplog: pytest.LogCaptureFixture
) -> None:
    resolver = SecretResolver()
    path = "datasources/security-regression/password"
    first_value = "initial-password-sentinel"
    updated_value = "updated-password-sentinel"
    registry_marker = "registry-only-sentinel"
    # Register a distinct marker before capture to exercise registry contents
    # independently of the path used for subsequent operations.
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
        resolver.set_secret(path, first_value)
        resolver.clean()
        assert resolver.list_secrets() == []
        assert not fake_secret_backend

    records = [record for record in caplog.records if record.name == "datam8.secrets"]
    assert records, "DEBUG logging must be exercised"
    for record in records:
        assert not record.args
        for sensitive in (first_value, updated_value, registry_marker, path, "test-solution"):
            assert sensitive not in record.getMessage()


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
