from __future__ import annotations

import io
import json
import urllib.error

import polars as pl
import pytest

from datam8.plugins.base import Plugin, TableMetadata
from datam8.plugins.builtins import databricks_uc


def load_plugin_module():
    return databricks_uc


@pytest.mark.parametrize("mode", ["pat", "oauthClientCredentials", "azureServicePrincipal"])
def test_real_auth_navigation_metadata_preview(mode, make_plugin, workspace, monkeypatch):
    plugin = make_plugin(mode)
    assert isinstance(plugin, Plugin)
    assert not plugin.__abstractmethods__
    monkeypatch.setattr(
        plugin,
        "_entra_token_url",
        lambda tenant: workspace.url + f"/{tenant}/oauth2/v2.0/token",
    )
    assert plugin.test_connection() is None
    schemas = plugin.list_source().to_dicts()
    assert [row["schema"] for row in schemas] == ["main.sales", "main.empty"]
    tables = plugin.list_source("main.sales").to_dicts()
    assert [row["type"] for row in tables] == ["MANAGED", "VIEW"]
    assert tables[0]["sourceLocation"] == "[main.sales].[Customers]"
    assert tables[0]["sourceOverride"] == {"sourceLocation": "`main`.`sales`.`Customers`"}
    metadata = plugin.get_table_metadata(tables[0]["sourceLocation"])
    assert isinstance(metadata, TableMetadata)
    fields = list(metadata.iter_source_fields())
    assert [field.ordinal for field in fields] == [1, 2, 3, 4, 5]
    assert fields[0].isPrimaryKey and not fields[0].isNullable
    assert fields[0].description == "Customer key"
    assert fields[1].maxLength == 80
    assert fields[2].numericPrecision == 10 and fields[2].numbericScale == 0
    assert fields[4].dataType == "struct<city:string>"
    assert plugin.resolve_source_type(fields[4].dataType) == "string"
    assert metadata.source_object.description == "CRM customers"
    preview = plugin.preview_data(tables[0]["sourceLocation"], limit=2)
    assert isinstance(preview, pl.LazyFrame)
    assert preview.collect().to_dicts() == [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": None},
    ]
    assert len(
        [request for request in workspace.requests if request["path"].endswith("/token")]
    ) == (0 if mode == "pat" else 1)


@pytest.mark.parametrize("mode", ["oauthClientCredentials", "azureServicePrincipal"])
def test_token_cache_across_instances_and_expiry(mode, make_plugin, workspace, monkeypatch):
    plugin = make_plugin(mode)
    monkeypatch.setattr(
        type(plugin),
        "_entra_token_url",
        lambda self, tenant: workspace.url + f"/{tenant}/oauth2/v2.0/token",
    )
    plugin.test_connection()
    make_plugin(mode).test_connection()
    assert len([r for r in workspace.requests if r["path"].endswith("/token")]) == 1
    key, (token, _) = next(iter(plugin._tokens.items()))
    plugin._tokens[key] = (token, 0)
    plugin.test_connection()
    assert len([r for r in workspace.requests if r["path"].endswith("/token")]) == 2


@pytest.mark.parametrize("mode", ["", " pat "])
def test_auth_mode_normalization(mode, make_plugin):
    assert make_plugin(authMode=mode).test_connection() is None


@pytest.mark.parametrize(
    "location",
    [
        "main.sales.Customers",
        "[main.sales].[Customers]",
        "[main].[sales].[Customers]",
        "`main`.`sales`.`Customers`",
    ],
)
def test_locations_round_trip(location, make_plugin):
    plugin = make_plugin()
    assert plugin.parse_source_location(location) == ("main", "sales", "Customers")
    assert list(plugin.get_table_metadata(location).iter_source_fields())[0].name == "id"


@pytest.mark.parametrize(
    "location",
    ["main.sales.Customers", "[main.sales].[Customers]", "`main`.`sales`.`Customers`"],
)
def test_source_definitions_use_one_location_for_metadata_and_data(location, make_plugin):
    definitions = make_plugin().get_sources(location)

    assert {row["metadataLocation"] for row in definitions} == {None}
    assert {row["sourceLocation"] for row in definitions} == {"`main`.`sales`.`Customers`"}
    assert [(row["sourceName"], row["targetName"]) for row in definitions] == [
        (name, name) for name in ("id", "name", "amount", "active", "details")
    ]
    assert definitions[1]["sourceDataType"]["charLen"] == 80
    assert definitions[2]["sourceDataType"]["precision"] == 10
    assert definitions[2]["sourceDataType"]["scale"] == 0
    assert definitions[4]["sourceDataType"]["type"] == "struct<city:string>"


@pytest.mark.parametrize(
    "location",
    [
        "",
        "Customers",
        "main..Customers",
        "main.sales.",
        "[main.sales].[Customers",
        "main.sales.Customers.extra",
    ],
)
def test_invalid_locations(location):
    with pytest.raises(ValueError):
        load_plugin_module().DatabricksUnityCatalog.parse_source_location(location)


@pytest.mark.parametrize(
    "source_type,target",
    [
        ("LONG", "long"),
        ("int", "int"),
        ("tinyint", "byte"),
        ("smallint", "short"),
        ("boolean", "bit"),
        ("decimal(10,0)", "decimal"),
        ("timestamp_ntz", "datetime"),
        ("array<string>", "string"),
        ("map<string,int>", "string"),
        ("variant", "string"),
    ],
)
def test_type_resolution(source_type, target):
    assert load_plugin_module().DatabricksUnityCatalog.resolve_source_type(source_type) == target


def test_filters_and_empty_results(make_plugin, workspace):
    plugin = make_plugin(catalog="main", schema="sales")
    assert plugin.list_source().height == 1
    assert not any(r["path"].endswith("/catalogs") for r in workspace.requests)
    assert plugin.list_source("main.empty").height == 0
    assert "name" in plugin.list_source("main.empty").columns


def test_repeated_page_token_stops(make_plugin, workspace):
    workspace.repeat_page = True
    with pytest.raises(RuntimeError, match="repeated pagination"):
        make_plugin().test_connection()


def test_unknown_type_and_no_columns(make_plugin, workspace):
    workspace.columns[0]["type_text"] = "unsupported"
    fields = list(make_plugin().get_table_metadata("main.sales.Customers").iter_source_fields())
    assert fields[0].dataType == "unsupported"


def test_metadata_keeps_complex_field_case_and_ignores_zero_precision(make_plugin, workspace):
    workspace.columns[0].update(type_precision=0, type_scale=0, type_text="BIGINT")
    workspace.columns[4]["type_text"] = "STRUCT<City:STRING>"
    fields = list(make_plugin().get_table_metadata("main.sales.Customers").iter_source_fields())
    assert fields[0].numericPrecision is None and fields[0].numbericScale is None
    assert fields[0].dataType == "BIGINT"
    assert fields[4].dataType == "STRUCT<City:STRING>"
    workspace.columns = []
    with pytest.raises(ValueError, match="no column metadata"):
        make_plugin().get_table_metadata("main.sales.Customers")


def test_metadata_preserves_original_type_text_without_losing_size(make_plugin, workspace):
    workspace.columns[0].update(type_text=" DECIMAL(18,0) ", type_precision=None, type_scale=None)
    field = next(make_plugin().get_table_metadata("main.sales.Customers").iter_source_fields())
    assert field.dataType == " DECIMAL(18,0) "
    assert field.numericPrecision == 18 and field.numbericScale == 0


def test_secret_resolution_failure_never_falls_back(make_plugin, workspace):
    with pytest.raises(ValueError, match="Could not resolve secret ref"):
        make_plugin(token="ref://datasources/UC/missing").test_connection()
    assert workspace.requests == []


@pytest.mark.parametrize(
    "changes",
    [
        {"token": "plaintext"},
        {"token": ""},
        {"authMode": "wrong"},
        {"workspace_url": "http://external.example"},
        {"workspace_url": "https://user:password@example.com"},
        {"http_path": "/sql/protocolv1/cluster"},
        {"warehouse_id": "other", "http_path": "/sql/1.0/warehouses/warehouse1"},
    ],
)
def test_invalid_configuration(changes, make_plugin):
    with pytest.raises((ValueError, Exception)):
        make_plugin(**changes)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 302])
def test_safe_http_errors(status, make_plugin, workspace):
    workspace.error = status
    with pytest.raises(RuntimeError) as caught:
        make_plugin().test_connection()
    assert f"HTTP {status}" in str(caught.value)
    assert all(
        secret not in str(caught.value)
        for secret in ["developer-pat", "client-secret", "NEVER-ECHO-THIS"]
    )
    assert len(workspace.requests) == 1


def test_network_error_does_not_expose_transport_details(make_plugin, monkeypatch):
    plugin = make_plugin()

    def fail(*args, **kwargs):
        raise urllib.error.URLError("developer-pat client-secret")

    monkeypatch.setattr(plugin._opener, "open", fail)
    with pytest.raises(RuntimeError) as caught:
        plugin.test_connection()
    assert "network" in str(caught.value).lower()
    assert "developer-pat" not in str(caught.value) and "client-secret" not in str(caught.value)


def test_invalid_json_response_is_safe(make_plugin, monkeypatch):
    plugin = make_plugin()
    monkeypatch.setattr(
        plugin._opener,
        "open",
        lambda *args, **kwargs: io.BytesIO(b"developer-pat client-secret"),
    )
    with pytest.raises(RuntimeError) as caught:
        plugin.test_connection()
    assert "JSON" in str(caught.value)
    assert "developer-pat" not in str(caught.value) and "client-secret" not in str(caught.value)


@pytest.mark.parametrize("limit", [0, -1, 1001, True, "10"])
def test_invalid_preview_limits(limit, make_plugin, workspace):
    with pytest.raises(ValueError, match="Preview limit"):
        make_plugin().preview_data("main.sales.Customers", limit=limit)
    assert workspace.requests == []


def test_preview_requires_warehouse_but_metadata_does_not(make_plugin):
    plugin = make_plugin(warehouse_id="")
    assert plugin.test_connection() is None
    with pytest.raises(ValueError, match="requires warehouse_id"):
        plugin.preview_data("main.sales.Customers")


def test_http_path_preview_and_sql_quoting(make_plugin, workspace):
    plugin = make_plugin(warehouse_id="", http_path="/sql/1.0/warehouses/warehouse1")
    plugin.preview_data("`main`.`sales`.`odd``name`", limit=1)
    data = json.loads(workspace.requests[-1]["body"])
    assert data["statement"] == "SELECT * FROM `main`.`sales`.`odd``name` LIMIT 1"
    assert data["row_limit"] == 1 and data["disposition"] == "INLINE"


def test_preview_chunks_and_empty_result(make_plugin, workspace):
    workspace.chunked = True
    assert make_plugin().preview_data("main.sales.Customers", limit=2).collect().height == 2
    workspace.chunked = False
    workspace.empty_preview = True
    result = make_plugin().preview_data("main.sales.Customers").collect()
    assert result.height == 0 and result.columns == ["id", "name"]


@pytest.mark.parametrize("state", ["FAILED", "CANCELED", "PENDING", "RUNNING"])
def test_preview_failure_and_cancellation(state, make_plugin, workspace):
    workspace.preview_state = state
    with pytest.raises(RuntimeError) as caught:
        make_plugin().preview_data("main.sales.Customers")
    assert "NEVER-ECHO-THIS" not in str(caught.value)
    assert any(r["path"].endswith("/cancel") for r in workspace.requests) == (
        state in {"PENDING", "RUNNING"}
    )


@pytest.mark.parametrize("mode", ["pat", "oauthClientCredentials", "azureServicePrincipal"])
def test_preview_shares_budget_across_auth_statement_and_chunks(
    mode, make_plugin, workspace, monkeypatch
):
    plugin = make_plugin(mode)
    monkeypatch.setattr(plugin, "_entra_token_url", lambda tenant: workspace.url + "/token")
    clock = [100.0]
    monkeypatch.setattr(databricks_uc.time, "monotonic", lambda: clock[0])
    transport = plugin._transport
    calls = []
    opened = []
    open_request = plugin._opener.open

    def budgeted_open(request, *, timeout):
        opened.append(timeout)
        return open_request(request, timeout=timeout)

    monkeypatch.setattr(plugin._opener, "open", budgeted_open)

    def timed_transport(url, **kwargs):
        calls.append((url, clock[0], kwargs.get("timeout", 20), kwargs["deadline"]))
        result = transport(url, **kwargs)
        if url.endswith("/token"):
            clock[0] += 7
        elif url.endswith("/statements"):
            clock[0] += 12
            result["result"] = {"data_array": [["1", "Alice"]], "next_chunk_index": 1}
        else:
            index = int(url.rsplit("/", 1)[1])
            clock[0] += 10 if index == 1 else 9
            result = {"data_array": [[str(index + 1), None]], "next_chunk_index": index + 1}
        return result

    monkeypatch.setattr(plugin, "_transport", timed_transport)
    # Late responses must be rejected even if a transport returns after its timeout.
    with pytest.raises(RuntimeError, match="30-second time budget"):
        plugin.preview_data("main.sales.Customers", limit=10)
    assert len([url for url, *_ in calls if "/result/chunks/" in url]) == 2
    assert {deadline for *_, deadline in calls} == {130.0}
    assert opened == ([30.0, 18.0, 8.0] if mode == "pat" else [20.0, 23.0, 11.0, 1.0])
    statement = next(r for r in workspace.requests if r["path"].endswith("/statements"))
    assert json.loads(statement["body"])["wait_timeout"] == ("30s" if mode == "pat" else "23s")


@pytest.mark.parametrize("duration", [26.0, 30.0])
def test_preview_does_not_submit_sql_after_auth_exhausts_budget(duration, make_plugin, monkeypatch):
    plugin = make_plugin("oauthClientCredentials")
    clock = [100.0]
    monkeypatch.setattr(databricks_uc.time, "monotonic", lambda: clock[0])
    calls = []

    def token_transport(url, **kwargs):
        calls.append(url)
        clock[0] += duration
        return {"access_token": "oauth-token", "expires_in": 3600}

    monkeypatch.setattr(plugin, "_transport", token_transport)
    with pytest.raises(RuntimeError, match="30-second time budget"):
        plugin.preview_data("main.sales.Customers")
    assert len(calls) == 1 and calls[0].endswith("/token")


def test_preview_token_lock_wait_uses_remaining_budget(make_plugin, monkeypatch):
    plugin = make_plugin("oauthClientCredentials")
    clock = [100.0]
    monkeypatch.setattr(databricks_uc.time, "monotonic", lambda: clock[0])
    timeouts = []

    class BusyLock:
        def acquire(self, *, timeout):
            timeouts.append(timeout)
            clock[0] += timeout
            return False

    monkeypatch.setattr(plugin, "_token_lock", BusyLock())
    with pytest.raises(RuntimeError, match="30-second time budget"):
        plugin.preview_data("main.sales.Customers")
    assert timeouts == [30.0]


@pytest.mark.parametrize("cancel_failure", [False, True])
def test_preview_cancel_preserves_timeout_and_uses_remaining_budget(
    cancel_failure, make_plugin, workspace, monkeypatch
):
    plugin = make_plugin()
    workspace.preview_state = "RUNNING"
    clock = [100.0]
    monkeypatch.setattr(databricks_uc.time, "monotonic", lambda: clock[0])
    transport = plugin._transport
    cancel = []

    def timed_transport(url, **kwargs):
        if url.endswith("/cancel"):
            cancel.append((clock[0], kwargs["deadline"]))
            clock[0] += 3
            if cancel_failure:
                raise RuntimeError("cancel failed client-secret")
        result = transport(url, **kwargs)
        if url.endswith("/statements"):
            clock[0] += 28
        return result

    monkeypatch.setattr(plugin, "_transport", timed_transport)
    with pytest.raises(RuntimeError, match="30-second time budget") as caught:
        plugin.preview_data("main.sales.Customers")
    assert cancel == [(128.0, 130.0)]
    assert "client-secret" not in str(caught.value)
    assert not any(r["path"].endswith("/cancel") for r in workspace.requests)


def test_preview_transport_reduces_timeout_after_headers(make_plugin, monkeypatch):
    from types import SimpleNamespace

    plugin = make_plugin()
    clock = [100.0]
    monkeypatch.setattr(databricks_uc.time, "monotonic", lambda: clock[0])
    timeouts = []

    class SlowBody(io.BytesIO):
        def read1(self, size):
            clock[0] += 21
            return super().read1(size)

    response = SlowBody(b'{"result": {}}')
    response.fp = SimpleNamespace(
        raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=timeouts.append))
    )

    def open_response(*args, **kwargs):
        clock[0] += 10
        return response

    monkeypatch.setattr(plugin._opener, "open", open_response)
    with pytest.raises(RuntimeError, match="30-second time budget"):
        plugin._transport("https://example.com", timeout=30, deadline=130.0)
    assert timeouts == [20.0]
