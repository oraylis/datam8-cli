from __future__ import annotations

from datam8.core import schema_refresh


class _FakeConnector:
    @staticmethod
    def get_table_metadata(_cfg, _resolver, _schema: str, _table: str):
        return {
            "columns": [
                {
                    "name": "Id",
                    "dataType": "int",
                    "isNullable": False,
                    "maxLength": None,
                    "numericPrecision": 10,
                    "numericScale": 0,
                    "isPrimaryKey": True,
                },
                {
                    "name": "Amount",
                    "dataType": "decimal",
                    "isNullable": True,
                    "maxLength": None,
                    "numericPrecision": 18,
                    "numericScale": 4,
                    "isPrimaryKey": False,
                },
                {
                    "name": "CreatedAt",
                    "dataType": "TIMESTAMP(6)",
                    "isNullable": True,
                    "maxLength": 11,
                    "numericPrecision": None,
                    "numericScale": None,
                    "isPrimaryKey": False,
                },
            ]
        }


def test_supports_precision_scale_only_for_decimal_families() -> None:
    assert schema_refresh._supports_precision_scale("decimal")
    assert schema_refresh._supports_precision_scale("NUMBER(18,4)")
    assert not schema_refresh._supports_precision_scale("money")
    assert not schema_refresh._supports_precision_scale("int")
    assert not schema_refresh._supports_precision_scale("varchar")


def test_supports_char_len_only_for_len_types() -> None:
    assert schema_refresh._supports_char_len("varchar")
    assert schema_refresh._supports_char_len("RAW")
    assert not schema_refresh._supports_char_len("TIMESTAMP(6)")
    assert not schema_refresh._supports_char_len("int")


def test_fetch_source_metadata_drops_precision_scale_for_int(monkeypatch) -> None:
    monkeypatch.setattr(
        schema_refresh,
        "resolve_and_validate",
        lambda **_kwargs: (_FakeConnector, {"id": "sqlserver"}, {}, object()),
    )
    monkeypatch.setattr(schema_refresh, "require_capability", lambda *_args, **_kwargs: None)

    out = schema_refresh.fetch_source_metadata(
        solution_path=None,
        data_source_name="Demo",
        source_location="dbo.Users",
        runtime_secrets=None,
    )

    id_col = next(col for col in out if col.get("name") == "Id")
    amount_col = next(col for col in out if col.get("name") == "Amount")
    created_at_col = next(col for col in out if col.get("name") == "CreatedAt")

    assert id_col["dataType"]["type"] == "int"
    assert "precision" not in id_col["dataType"]
    assert "scale" not in id_col["dataType"]

    assert amount_col["dataType"]["type"] == "decimal"
    assert amount_col["dataType"]["precision"] == 18
    assert amount_col["dataType"]["scale"] == 4
    assert created_at_col["dataType"]["type"] == "TIMESTAMP(6)"
    assert "charLen" not in created_at_col["dataType"]


def test_safe_merge_drops_stale_precision_for_non_decimal_types() -> None:
    merged_xml = schema_refresh.safe_merge_data_type(
        {"type": "decimal", "nullable": True, "precision": 18, "scale": 4},
        {"type": "xml", "nullable": True},
    )
    assert merged_xml["type"] == "xml"
    assert "precision" not in merged_xml
    assert "scale" not in merged_xml

    merged_money = schema_refresh.safe_merge_data_type(
        {"type": "decimal", "nullable": True, "precision": 18, "scale": 4},
        {"type": "money", "nullable": True},
    )
    assert merged_money["type"] == "money"
    assert "precision" not in merged_money
    assert "scale" not in merged_money


def test_safe_merge_drops_stale_char_len_for_non_len_types() -> None:
    merged_ts = schema_refresh.safe_merge_data_type(
        {"type": "varchar", "nullable": True, "charLen": 42},
        {"type": "TIMESTAMP(6)", "nullable": True},
    )
    assert merged_ts["type"] == "TIMESTAMP(6)"
    assert "charLen" not in merged_ts
