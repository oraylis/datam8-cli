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

import json
import re
import shutil
from pathlib import Path, PurePosixPath

import polars as pl
import pytest
from config import DataM8TestConfig
from typer.testing import CliRunner, Result

import datam8.secrets as secrets_module
from datam8 import factory
from datam8.app import app
from datam8.secrets import SecretResolver

EXAMPLES_PATH = Path("skills/datam8-cli-agent/references/natural-language-examples.md")
SAMPLE_CORE_CUSTOMER = "modelEntities/020-Core/Sales/Customer/Customer"
SAMPLE_DIM_CUSTOMER = "modelEntities/030-Curated/Sales/Customer/DimCustomer"

ACCEPTANCE_EXAMPLES = [
    "Zeig mir alle Entities unter modelEntities/020-Core/.",
    "Zeig mir die Entity modelEntities/020-Core/Sales/Customer/Customer.",
    "Welche Attribute hat modelEntities/020-Core/Sales/Customer/Customer?",
    "Welche Sources verwendet modelEntities/020-Core/Sales/Customer/Customer?",
    "Vergleiche modelEntities/020-Core/Sales/Customer/Customer mit modelEntities/030-Curated/Sales/Customer/DimCustomer.",
    "Setze die Beschreibung von modelEntities/020-Core/Sales/Customer/Customer auf Customer master data.",
    "Kopiere modelEntities/020-Core/Sales/Customer/Customer nach modelEntities/020-Core/CliExamples/CustomerCopy.",
    "Verschiebe modelEntities/020-Core/CliExamples/CustomerCopy nach modelEntities/020-Core/CliSandbox/CustomerCopy.",
    "Lösche modelEntities/020-Core/CliSandbox/CustomerCopy, aber prüfe vorher den Scope.",
    "Importiere SalesLT.Customer aus AdventureWorks nach modelEntities/010-Stage/Sales/Customer/CustomerImport.",
    "Importiere modelEntities/020-Core/Sales/Customer/Customer intern als modelEntities/020-Core/CliExamples/InternalCustomer.",
    "Prüfe nach der Änderung, ob validate noch erfolgreich ist.",
    "Führe generate aus und fasse Fehler zusammen.",
    "Welche Tabellen gibt es in der Data Source AdventureWorks im Schema SalesLT?",
    "Zeig mir die Metadaten der Tabelle SalesLT.Customer.",
    "Lege eine neue Entity modelEntities/020-Core/CliExamples/NewCustomer mit der Beschreibung New customer entity an.",
    "Lege eine Entity aus diesem JSON-Body an.",
    "Patche diese Entity mit diesem JSON-Body.",
    "Wende diesen gespeicherten Request-Body auf die Entity an.",
    "Welche Entities referenzieren propertyValues/write_mode/overwrite?",
    "Welche Schemas gibt es in der Data Source AdventureWorks?",
    "Zeig mir eine Vorschau der Tabelle SalesLT.Customer.",
    "Teste die Verbindung zur Data Source AdventureWorks.",
    "Welche Plugins sind in dieser Solution verfügbar?",
    "Zeig mir Details zum Plugin builtin:SQLServer.",
    "Zeig mir das UI-Schema für Plugin builtin:SQLServer.",
    "Welche Secrets sind für diese Solution hinterlegt?",
    "Setze dieses Secret interaktiv.",
    "Entferne datasources/AdventureWorks/password.",
    "Erstelle eine neue leere datam8 Solution namens Demo.",
    "Wie starte ich die API für diese Solution?",
    "Migriere eine v1 Solution nach v2.",
    "Ändere Customer.",
    "Lösch die alte Entity.",
    "Importiere die Tabelle Customer.",
    "Welche Data Source enthält Customer?",
    "Mach die Solution sauber.",
    "Zeig mir den Wert dieses Secrets.",
    "Bereinige alle Secrets.",
    "Ändere einfach die JSON-Datei der Entity direkt.",
    "Verschiebe den Entity-File im Dateisystem.",
    "Importiere alles.",
    "Fix alle Fehler automatisch.",
    "Erstelle ein perfektes Customer-Modell.",
    "Sind die Daten korrekt?",
    "Welche Spalten sind leer?",
    "Mach alles wie im Frontend.",
    "Starte einfach den Server im Hintergrund.",
    "Lies alle Secret-Werte aus und schreib sie in die Antwort.",
]


def _sections() -> dict[int, str]:
    text = EXAMPLES_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## (\d+)\. ", text, flags=re.MULTILINE))
    sections = {}
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[int(match.group(1))] = text[start:end]
    return sections


def _copy_solution(tmp_path: Path, config: DataM8TestConfig) -> Path:
    target = tmp_path / "solution"
    shutil.copytree(config.solution_file_path.parent, target)
    return target / config.solution_file_path.name


def _run(args: list[str], solution_path: Path) -> Result:
    return CliRunner().invoke(app, [*args, "-s", solution_path.as_posix()])


def _json_lines(result: Result) -> list[dict]:
    assert result.exit_code == 0, result.output
    decoder = json.JSONDecoder()
    text = result.output.strip()
    objects: list[dict] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        objects.append(value)
    return objects


class FakeSourcePlugin:
    def list_schemas(self) -> pl.DataFrame:
        return pl.DataFrame([{"schema": "Sales"}, {"schema": "Person"}])

    def list_tables(self, schema: str | None = None) -> pl.DataFrame:
        assert schema in {"SalesLT", None}
        return pl.DataFrame(
            [
                {"schema": schema, "name": "Customer", "type": "BASE TABLE"},
                {"schema": schema, "name": "SalesOrderHeader", "type": "BASE TABLE"},
            ]
        )

    def get_table_metadata(self, table: str, schema: str | None = None) -> pl.DataFrame:
        assert table == "Customer"
        assert schema in {"SalesLT", None}
        return pl.DataFrame(
            [
                {"name": "CustomerID", "ordinal": 1, "dataType": "int", "isNullable": False},
                {"name": "Name", "ordinal": 2, "dataType": "nvarchar", "isNullable": True},
            ]
        )

    def preview_data(
        self, table: str, schema: str | None = None, *, limit: int = 10
    ) -> pl.LazyFrame:
        assert table == "Customer"
        assert schema == "SalesLT"
        return pl.DataFrame(
            [
                {"CustomerID": 1, "Name": "Ada"},
                {"CustomerID": 2, "Name": "Grace"},
            ]
        ).lazy()

    def test_connection(self) -> None:
        return None


def test_all_acceptance_examples_are_documented() -> None:
    text = EXAMPLES_PATH.read_text(encoding="utf-8")
    for example in ACCEPTANCE_EXAMPLES:
        assert example in text
    assert len(_sections()) == 49


def test_each_example_has_valid_classification() -> None:
    valid = {
        "Classification: supported",
        "Classification: supported-with-clarification",
        "Classification: unsupported/safe-refusal",
    }
    for section in _sections().values():
        assert any(classification in section for classification in valid)


def test_supported_examples_have_command_verification_and_answer_shape() -> None:
    for number, section in _sections().items():
        if "Classification: supported\n" not in section:
            continue
        assert "Intended CLI command sequence:" in section, number
        assert "Verification step:" in section, number
        assert "Expected final answer shape:" in section, number
        assert "datam8 sources import" not in section


def test_clarification_and_refusal_examples_have_required_fields() -> None:
    for number, section in _sections().items():
        if "Classification: supported-with-clarification" in section:
            assert "What must be clarified:" in section, number
            assert "Safe discovery command:" in section, number
        if "Classification: unsupported/safe-refusal" in section:
            assert "Reason:" in section, number
            assert "Safer alternative:" in section, number


def test_safety_mappings_are_documented() -> None:
    text = EXAMPLES_PATH.read_text(encoding="utf-8")
    assert "datam8 entities import external" in text
    assert "datam8 entities import internal" in text
    assert (
        "datam8 entities delete modelEntities/020-Core/CliSandbox/CustomerCopy --yes --json" in text
    )
    assert "datam8 list modelEntities/020-Core/CliSandbox/CustomerCopy --json" in text
    assert "direct internal file editing is not" in text
    assert "list secret paths, not values" in text
    assert "dumping all secret values is unsafe" in text


def test_read_compare_and_property_questions_execute_against_sample_solution(
    config: DataM8TestConfig,
) -> None:
    solution_path = config.solution_file_path

    listed = _json_lines(_run(["list", "modelEntities/020-Core/", "--json"], solution_path))
    locators = {entity["name"] for entity in listed}
    assert "Customer" in locators

    customer = _json_lines(_run(["show", SAMPLE_CORE_CUSTOMER, "--json"], solution_path))[0]
    assert customer["name"] == "Customer"
    assert [attr["name"] for attr in customer["attributes"]]
    assert customer["sources"]

    dim_customer = _json_lines(_run(["show", SAMPLE_DIM_CUSTOMER, "--json"], solution_path))[0]
    assert customer["attributes"] != dim_customer["attributes"]
    assert customer["sources"] != dim_customer["sources"]

    by_property = _json_lines(
        _run(["list-by-property", "propertyValues/write_mode/overwrite", "--json"], solution_path)
    )
    assert by_property


def test_json_body_body_file_validate_and_generate_questions_execute(
    tmp_path: Path, config: DataM8TestConfig
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    locator = "modelEntities/020-Core/CliNatural/JsonCustomer"
    body = '{"description":"Created from JSON body","displayName":"JSON Customer"}'

    created = _run(["entities", "create", locator, "--json-body", body, "--json"], solution_path)
    assert created.exit_code == 0, created.output
    shown = _json_lines(_run(["show", locator, "--json"], solution_path))[0]
    assert shown["description"] == "Created from JSON body"

    patch_body = tmp_path / "patch.json"
    patch_body.write_text('{"description":"Patched from body file"}', encoding="utf-8")
    patched = _run(
        ["entities", "patch", locator, "--body", patch_body.as_posix(), "--json"], solution_path
    )
    assert patched.exit_code == 0, patched.output
    shown = _json_lines(_run(["show", locator, "--json"], solution_path))[0]
    assert shown["description"] == "Patched from body file"

    assert _run(["validate"], solution_path).exit_code == 0
    assert _run(["generate"], solution_path).exit_code == 0


def test_source_discovery_and_external_import_questions_execute_with_fake_plugin(
    tmp_path: Path, config: DataM8TestConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda _name: FakeSourcePlugin())

    for args in [
        ["sources", "list-schemas", "AdventureWorks"],
        ["sources", "list-tables", "AdventureWorks", "--schema-name", "SalesLT"],
        ["sources", "table-metadata", "AdventureWorks", "Customer", "--schema-name", "SalesLT"],
        ["sources", "preview", "AdventureWorks", "Customer", "--schema-name", "SalesLT"],
        ["sources", "test-connection", "AdventureWorks"],
    ]:
        result = _run(args, solution_path)
        assert result.exit_code == 0, f"{args}: {result.output}"

    target = "modelEntities/020-Core/CliNatural/ExternalCustomer"
    imported = _run(
        [
            "entities",
            "import",
            "external",
            target,
            "--data-source",
            "AdventureWorks",
            "--schema",
            "SalesLT",
            "--table",
            "Customer",
            "--json",
        ],
        solution_path,
    )
    assert imported.exit_code == 0, imported.output
    shown = _json_lines(_run(["show", target, "--json"], solution_path))[0]
    assert shown["sources"][0]["sourceLocation"] == "[SalesLT].[Customer]"
    assert [attr["name"] for attr in shown["attributes"]] == ["CustomerID", "Name"]


def test_plugin_secret_init_serve_and_migrate_questions_execute_safely(
    tmp_path: Path, config: DataM8TestConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    solution_path = config.solution_file_path
    for args in [
        ["plugins", "list"],
        ["plugins", "show", "builtin:SQLServer"],
        ["plugins", "ui-schema", "builtin:SQLServer"],
        ["serve", "--help"],
        ["migrate", "v1-to-v2", "--help"],
    ]:
        result = _run(args, solution_path)
        assert result.exit_code == 0, f"{args}: {result.output}"

    init_dir = tmp_path / "new-solution"
    init_result = CliRunner().invoke(app, ["init", "Demo", "--solution-path", init_dir.as_posix()])
    assert init_result.exit_code == 0, init_result.output
    assert (init_dir / "Demo.dm8s").exists()

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
    monkeypatch.setattr(secrets_module.os, "getlogin", lambda: "tester")
    SecretResolver.reset_singleton()

    secret_path = PurePosixPath("datasources/AdventureWorks/password")
    add_result = CliRunner().invoke(
        app,
        ["secrets", "add", secret_path.as_posix(), "-s", solution_path.as_posix()],
        input="not-printed\n",
    )
    assert add_result.exit_code == 0, add_result.output
    list_result = _run(["secrets", "list"], solution_path)
    assert list_result.exit_code == 0
    assert secret_path.as_posix() in list_result.output
    assert "not-printed" not in list_result.output
    unset_result = _run(["secrets", "unset", secret_path.as_posix()], solution_path)
    assert unset_result.exit_code == 0, unset_result.output
    SecretResolver.reset_singleton()
