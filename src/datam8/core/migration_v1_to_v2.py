from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datam8.core.errors import Datam8ValidationError
from datam8.core.workspace_io import regenerate_index


@dataclass
class _V1RawEntityInfo:
    key: str
    data_product: str
    data_module: str
    name: str
    display_name: str | None
    rel_path_to_v1_json: str
    function: dict[str, str] | None
    attributes: list[dict[str, Any]]
    v1: dict[str, Any]


@dataclass
class _V1EntityMeta:
    src_abs_path: Path | None
    zone: str  # "stage" | "core" | "curated" | "consumer"
    data_product: str
    data_module: str
    name: str
    display_name: str | None
    v1_locators: list[str]
    v2_rel_path: str
    entity_id: int
    raw_key: str | None
    v1: dict[str, Any]


def _to_iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    s = (value or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = re.sub(r"^_+|_+$", "", s)
    return s


def _is_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value.keys()) > 0
    return True


def _warn_dropped_fields(warnings: list[str], context: str, source: Any, kept: set[str]) -> None:
    if not isinstance(source, dict):
        return
    dropped = [k for k in source.keys() if k not in kept and _is_meaningful_value(source.get(k))]
    if dropped:
        warnings.append(f"{context}: dropped unsupported fields: {', '.join(sorted(dropped))}")


def _stringify_value(value: Any, warnings: list[str], context: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value)
    except Exception as e:
        warnings.append(f"{context}: failed to stringify parameter value ({e}); skipped.")
        return None


def _normalize_internal_type(v1_type: Any) -> str:
    t = v1_type.lower().strip() if isinstance(v1_type, str) else ""
    if not t:
        return "string"
    if t in {"string", "nvarchar", "varchar", "nchar", "char", "text"}:
        return "string"
    if t in {"bit", "bool", "boolean"}:
        return "boolean"
    if t in {"date", "datetime", "datetime2", "timestamp"}:
        return "datetime"
    if t in {"bigint", "long", "int64"}:
        return "long"
    if t in {"smallint", "short", "int", "integer", "int32"}:
        return "int"
    if t in {"float", "double", "real"}:
        return "double"
    if t in {"decimal", "numeric", "money"}:
        return "decimal"
    return "string"


def _normalize_v2_history(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if v in {"SCD0", "SCD1", "SCD2", "SCD3", "SCD4"} else None


def _to_datetime_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if re.match(r"^\\d{4}-\\d{2}-\\d{2}T", v):
        return v
    if re.match(r"^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$", v):
        return f"{v.replace(' ', 'T')}Z"
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _v1_zone_label(zone: str) -> str:
    return {
        "raw": "Raw",
        "stage": "Stage",
        "core": "Core",
        "curated": "Curated",
        "consumer": "Consumer",
    }[zone]


def _v2_zone_folder(zone: str) -> str:
    if zone == "stage":
        return "010-Stage"
    if zone == "core":
        return "020-Core"
    if zone == "curated":
        return "030-Curated"
    return "040-Consumer"


def _read_json(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def _write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def _is_dir_empty(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        return next(path.iterdir(), None) is None
    except Exception:
        return False


def _safe_cp(src: Path, dst: Path, copied_paths: list[str], warnings: list[str], label: str) -> None:
    try:
        if not src.exists():
            warnings.append(f"{label}: source folder not found; skipped.")
            return
        if not src.is_dir():
            warnings.append(f"{label}: source is not a directory; skipped.")
            return
        if dst.exists():
            warnings.append(f"{label}: destination already exists; skipped.")
            return
        shutil.copytree(src, dst)
        copied_paths.append(dst.as_posix())
    except Exception as e:
        warnings.append(f"{label}: copy failed ({e}); skipped.")


def _dedupe_property_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for ref in refs:
        prop = ref.get("property") or ""
        val = ref.get("value") or ""
        key = f"{prop}::{val}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"property": prop, "value": val})
    return out


def migrate_solution_v1_to_v2(args: dict[str, Any]) -> dict[str, Any]:
    started_at = _to_iso_now()
    warnings: list[str] = []
    errors: list[str] = []
    migrated_base_files: list[str] = []
    copied_paths: list[str] = []
    written_files = 0
    migrated_model_entities = 0

    source_solution_path = args.get("sourceSolutionPath")
    target_dir = args.get("targetDir")
    options_raw = args.get("options")
    options: dict[str, Any] = options_raw if isinstance(options_raw, dict) else {}
    copy_generate = bool(options.get("copyGenerate", True))
    copy_diagram = bool(options.get("copyDiagram", True))
    copy_output = bool(options.get("copyOutput", False))

    if not isinstance(source_solution_path, str) or not source_solution_path.strip() or not source_solution_path.lower().endswith(".dm8s"):
        raise Datam8ValidationError(message="sourceSolutionPath must point to a .dm8s file.", details=None)
    if not isinstance(target_dir, str) or not target_dir.strip():
        raise Datam8ValidationError(message="targetDir is required.", details=None)

    src_solution_file = Path(source_solution_path).expanduser().resolve()
    if not src_solution_file.exists():
        raise Datam8ValidationError(message="V1 solution file not found.", details={"path": str(src_solution_file)})

    try:
        v1_solution_raw = _read_json(src_solution_file)
    except Exception as e:
        raise Datam8ValidationError(message="Failed to read V1 solution file.", details={"error": str(e)})

    if not isinstance(v1_solution_raw, dict):
        raise Datam8ValidationError(message="sourceSolutionPath does not look like a V1 solution (.dm8s).", details=None)

    # V1 requires basePath + at least one of rawPath/stagingPath/corePath/curatedPath.
    base_path = v1_solution_raw.get("basePath")
    raw_path = v1_solution_raw.get("rawPath")
    staging_path = v1_solution_raw.get("stagingPath")
    core_path = v1_solution_raw.get("corePath")
    curated_path = v1_solution_raw.get("curatedPath")
    if not isinstance(base_path, str) or not base_path.strip() or not any(
        isinstance(p, str) and p.strip() for p in (raw_path, staging_path, core_path, curated_path)
    ):
        raise Datam8ValidationError(message="sourceSolutionPath does not look like a V1 solution (.dm8s).", details=None)

    src_root = src_solution_file.parent
    solution_name = src_solution_file.stem

    out_target_dir = Path(target_dir).expanduser().resolve()
    out_target_dir.mkdir(parents=True, exist_ok=True)

    if _is_dir_empty(out_target_dir):
        out_root = out_target_dir
    else:
        stamp = re.sub(r"[-:]", "", started_at)
        stamp = re.sub(r"\\..*$", "", stamp).replace("T", "-")
        out_root = out_target_dir / f"{solution_name}-v2-{stamp}"
        out_root.mkdir(parents=True, exist_ok=True)

    (out_root / "Base").mkdir(parents=True, exist_ok=True)
    (out_root / "Model").mkdir(parents=True, exist_ok=True)

    v1_base_dir = (src_root / str(base_path)).resolve()

    def read_v1_base(filename: str) -> Any:
        abs_path = v1_base_dir / filename
        try:
            return _read_json(abs_path)
        except Exception:
            warnings.append(f"Base/{filename}: missing or unreadable; generated fallback.")
            return None

    v1_attribute_types = read_v1_base("AttributeTypes.json")
    v1_data_products = read_v1_base("DataProducts.json")
    v1_data_sources = read_v1_base("DataSources.json")
    v1_data_types = read_v1_base("DataTypes.json")

    default_attribute_types = [
        {"name": "ID", "displayName": "ID", "defaultType": "int", "canBeInRelation": True, "isDefaultProperty": False},
        {
            "name": "Name",
            "displayName": "Name",
            "defaultType": "string",
            "defaultLength": 256,
            "canBeInRelation": False,
            "isDefaultProperty": True,
        },
        {
            "name": "Description",
            "displayName": "Description",
            "defaultType": "string",
            "defaultLength": 512,
            "canBeInRelation": False,
            "isDefaultProperty": False,
        },
    ]

    default_data_types = [
        {
            "name": "string",
            "displayName": "Unicode String",
            "description": "",
            "hasCharLen": True,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "string", "sqlserver": "nvarchar"},
        },
        {
            "name": "int",
            "displayName": "Integer (32 bit)",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "int", "sqlserver": "int"},
        },
        {
            "name": "long",
            "displayName": "Integer (64 bit)",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "bigint", "sqlserver": "bigint"},
        },
        {
            "name": "double",
            "displayName": "Double",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "double", "sqlserver": "float"},
        },
        {
            "name": "decimal",
            "displayName": "Decimal",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": True,
            "hasScale": True,
            "targets": {"databricks": "decimal", "sqlserver": "decimal"},
        },
        {
            "name": "datetime",
            "displayName": "DateTime",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "timestamp", "sqlserver": "datetime2"},
        },
        {
            "name": "boolean",
            "displayName": "Boolean",
            "description": "",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {"databricks": "boolean", "sqlserver": "bit"},
        },
    ]

    converted_attribute_types = []
    for a in (v1_attribute_types or {}).get("items", []) if isinstance(v1_attribute_types, dict) else []:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        converted_attribute_types.append(
            {
                "name": name,
                "displayName": a.get("displayName") if isinstance(a.get("displayName"), str) else name,
                "description": a.get("purpose") if isinstance(a.get("purpose"), str) else (a.get("description") if isinstance(a.get("description"), str) else ""),
                "defaultType": a.get("defaultType"),
                "defaultLength": a.get("defaultLength"),
                "defaultPrecision": a.get("defaultPrecision"),
                "defaultScale": a.get("defaultScale"),
                "hasUnit": a.get("hasUnit"),
                "canBeInRelation": a.get("canBeInRelation"),
                "isDefaultProperty": a.get("isDefaultProperty"),
            }
        )
    out_attribute_types = {"type": "attributeTypes", "attributeTypes": converted_attribute_types or default_attribute_types}

    out_data_products = {"type": "dataProducts", "dataProducts": []}
    for p in (v1_data_products or {}).get("items", []) if isinstance(v1_data_products, dict) else []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        modules = []
        for m in p.get("module", []) if isinstance(p.get("module"), list) else []:
            if not isinstance(m, dict):
                continue
            mname = m.get("name")
            if not isinstance(mname, str) or not mname.strip():
                continue
            modules.append(
                {
                    "name": mname,
                    "displayName": m.get("displayName") if isinstance(m.get("displayName"), str) else mname,
                    "description": m.get("purpose") if isinstance(m.get("purpose"), str) else "",
                }
            )
        out_data_products["dataProducts"].append(
            {
                "name": name,
                "displayName": p.get("displayName") if isinstance(p.get("displayName"), str) else name,
                "description": p.get("purpose") if isinstance(p.get("purpose"), str) else "",
                "dataModules": modules,
            }
        )

    out_data_sources = {"type": "dataSources", "dataSources": []}
    for s in (v1_data_sources or {}).get("items", []) if isinstance(v1_data_sources, dict) else []:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        out_data_sources["dataSources"].append(
            {
                "name": name,
                "displayName": s.get("displayName") if isinstance(s.get("displayName"), str) else name,
                "description": s.get("purpose") if isinstance(s.get("purpose"), str) else "",
                "type": s.get("type"),
                "connectionString": s.get("connectionString"),
                "dataTypeMapping": s.get("dataTypeMapping") if isinstance(s.get("dataTypeMapping"), list) else None,
                "extendedProperties": s.get("ExtendedProperties") if isinstance(s.get("ExtendedProperties"), dict) else None,
            }
        )

    converted_data_types = []
    for t in (v1_data_types or {}).get("items", []) if isinstance(v1_data_types, dict) else []:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        targets: dict[str, str] = {}
        parquet = t.get("parquetType")
        sql_type = t.get("sqlType")
        if isinstance(parquet, str) and parquet.strip():
            targets["databricks"] = parquet.strip()
        if isinstance(sql_type, str) and sql_type.strip():
            targets["sqlserver"] = sql_type.strip()
        if not targets:
            targets["databricks"] = name.strip()
            warnings.append(f"Base/DataTypes.json: '{name}' missing parquetType/sqlType; using fallback targets.")
        converted_data_types.append(
            {
                "name": name,
                "displayName": t.get("displayName") if isinstance(t.get("displayName"), str) else name,
                "description": t.get("purpose") if isinstance(t.get("purpose"), str) else (t.get("description") if isinstance(t.get("description"), str) else ""),
                "hasCharLen": bool(t.get("hasCharLen", False)),
                "hasPrecision": bool(t.get("hasPrecision", False)),
                "hasScale": bool(t.get("hasScale", False)),
                "targets": targets,
            }
        )
    out_data_types = {"type": "dataTypes", "dataTypes": converted_data_types or default_data_types}

    by_type: dict[str, list[dict[str, Any]]] = {}
    for ds in out_data_sources.get("dataSources") or []:
        t = ds.get("type")
        type_name = t.strip() if isinstance(t, str) and t.strip() else "Unknown"
        by_type.setdefault(type_name, []).append(ds)
    out_data_source_types = {"type": "dataSourceTypes", "dataSourceTypes": []}
    for type_name, sources in by_type.items():
        mappings: list[dict[str, str]] = []
        for s in sources:
            for row in s.get("dataTypeMapping") or []:
                if isinstance(row, dict) and isinstance(row.get("sourceType"), str) and isinstance(row.get("targetType"), str):
                    mappings.append({"sourceType": row["sourceType"], "targetType": row["targetType"]})
        uniq: dict[str, dict[str, str]] = {}
        for m in mappings:
            uniq[f"{m['sourceType']}::{m['targetType']}"] = m
        data_type_mapping = list(uniq.values())
        if not data_type_mapping:
            warnings.append(f"Base/DataSourceTypes.json: '{type_name}' has no dataTypeMapping; generated fallback mapping.")
            data_type_mapping = [{"sourceType": "string", "targetType": "string"}]
        out_data_source_types["dataSourceTypes"].append(
            {"name": type_name, "displayName": type_name, "description": "", "dataTypeMapping": data_type_mapping}
        )

    out_zones = {
        "type": "zones",
        "zones": [
            {"name": "raw", "targetName": "raw", "displayName": "Raw"},
            {"name": "stage", "targetName": "010-Stage", "displayName": "Stage", "localFolderName": "010-Stage"},
            {"name": "core", "targetName": "020-Core", "displayName": "Core", "localFolderName": "020-Core"},
            {"name": "curated", "targetName": "030-Curated", "displayName": "Curated", "localFolderName": "030-Curated"},
            {"name": "consumer", "targetName": "040-Consumer", "displayName": "Consumer", "localFolderName": "040-Consumer"},
        ],
    }

    raw_by_key: dict[str, _V1RawEntityInfo] = {}
    used_raw_keys: set[str] = set()

    if isinstance(raw_path, str) and raw_path.strip():
        for abs_path in sorted((src_root / raw_path).rglob("*.json")):
            if not abs_path.is_file():
                continue
            try:
                j = _read_json(abs_path)
            except Exception as e:
                warnings.append(f"Raw: failed to parse '{abs_path.relative_to(src_root).as_posix()}' ({e}); skipped.")
                continue
            ent = j.get("entity") if isinstance(j, dict) else {}
            ent = ent if isinstance(ent, dict) else {}
            dp_raw = ent.get("dataProduct")
            dm_raw = ent.get("dataModule")
            name_raw = ent.get("name")
            dn_raw = ent.get("displayName")
            data_product = dp_raw.strip() if isinstance(dp_raw, str) and dp_raw.strip() else "UnknownProduct"
            data_module = dm_raw.strip() if isinstance(dm_raw, str) and dm_raw.strip() else "UnknownModule"
            name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else abs_path.stem
            display_name = dn_raw.strip() if isinstance(dn_raw, str) and dn_raw.strip() else None
            key = f"{data_product}::{data_module}::{name}"

            attrs_raw = ent.get("attribute")
            attrs = attrs_raw if isinstance(attrs_raw, list) else []
            attributes = []
            for a in attrs:
                if not isinstance(a, dict):
                    continue
                aname = a.get("name") if isinstance(a.get("name"), str) else ""
                atype = a.get("type") if isinstance(a.get("type"), str) else (a.get("dataType") if isinstance(a.get("dataType"), str) else "")
                if not aname or not atype:
                    continue
                attributes.append(
                    {
                        "name": aname,
                        "type": atype,
                        "charLength": a.get("charLength") if isinstance(a.get("charLength"), (int, float)) else None,
                        "precision": a.get("precision") if isinstance(a.get("precision"), (int, float)) else None,
                        "scale": a.get("scale") if isinstance(a.get("scale"), (int, float)) else None,
                        "nullable": a.get("nullable") if isinstance(a.get("nullable"), bool) else None,
                    }
                )

            fn = j.get("function") if isinstance(j, dict) else None
            fn = fn if isinstance(fn, dict) else {}
            ds_raw = fn.get("dataSource")
            sl_raw = fn.get("sourceLocation")
            fn_data_source = ds_raw.strip() if isinstance(ds_raw, str) and ds_raw.strip() else None
            fn_source_location = sl_raw.strip() if isinstance(sl_raw, str) and sl_raw.strip() else None
            fn_info: dict[str, str] | None = None
            if fn_data_source or fn_source_location:
                tmp: dict[str, str] = {}
                if fn_data_source:
                    tmp["dataSource"] = fn_data_source
                if fn_source_location:
                    tmp["sourceLocation"] = fn_source_location
                fn_info = tmp or None

            if key in raw_by_key:
                warnings.append(f"Raw: duplicate entity key '{key}' detected; keeping first entry.")
                continue
            raw_by_key[key] = _V1RawEntityInfo(
                key=key,
                data_product=data_product,
                data_module=data_module,
                name=name,
                display_name=display_name,
                rel_path_to_v1_json=abs_path.relative_to(src_root).as_posix(),
                function=fn_info,
                attributes=attributes,
                v1=j if isinstance(j, dict) else {},
            )

    v1_entities: list[_V1EntityMeta] = []

    def scan_zone(zone: str, rel_dir: Any) -> None:
        if not isinstance(rel_dir, str) or not rel_dir.strip():
            return
        for abs_path in sorted((src_root / rel_dir).rglob("*.json")):
            if not abs_path.is_file():
                continue
            try:
                j = _read_json(abs_path)
            except Exception as e:
                warnings.append(f"Model: failed to parse '{abs_path.relative_to(src_root).as_posix()}' ({e}); skipped.")
                continue
            ent = j.get("entity") if isinstance(j, dict) else {}
            ent = ent if isinstance(ent, dict) else {}
            dp_raw = ent.get("dataProduct")
            dm_raw = ent.get("dataModule")
            name_raw = ent.get("name")
            dn_raw = ent.get("displayName")
            data_product = dp_raw.strip() if isinstance(dp_raw, str) and dp_raw.strip() else "UnknownProduct"
            data_module = dm_raw.strip() if isinstance(dm_raw, str) and dm_raw.strip() else "UnknownModule"
            name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else abs_path.stem
            display_name = dn_raw.strip() if isinstance(dn_raw, str) and dn_raw.strip() else None

            zone_folder = _v2_zone_folder(zone)
            v2_rel_path = "/".join(["Model", zone_folder, data_product, data_module, f"{name}.json"])
            v1_locators = [f"/{_v1_zone_label(zone)}/{data_product}/{data_module}/{name}"]
            raw_key = None
            if zone == "stage":
                raw_key = f"{data_product}::{data_module}::{name}"
                if raw_key in raw_by_key:
                    used_raw_keys.add(raw_key)
                    v1_locators.append(f"/{_v1_zone_label('raw')}/{data_product}/{data_module}/{name}")
                else:
                    warnings.append(f"Stage entity {raw_key} has no matching Raw entity; sourceDataType omitted.")

            v1_entities.append(
                _V1EntityMeta(
                    src_abs_path=abs_path,
                    zone=zone,
                    data_product=data_product,
                    data_module=data_module,
                    name=name,
                    display_name=display_name,
                    v1_locators=v1_locators,
                    v2_rel_path=v2_rel_path,
                    entity_id=0,
                    raw_key=raw_key,
                    v1=j if isinstance(j, dict) else {},
                )
            )

    scan_zone("stage", staging_path)
    scan_zone("core", core_path)
    scan_zone("curated", curated_path)

    for key, raw in raw_by_key.items():
        if key in used_raw_keys:
            continue
        used_raw_keys.add(key)
        warnings.append(f"Raw entity {key} had no Stage counterpart; created synthetic Stage entity.")
        zone_folder = _v2_zone_folder("stage")
        v2_rel_path = "/".join(["Model", zone_folder, raw.data_product, raw.data_module, f"{raw.name}.json"])
        v1_entities.append(
            _V1EntityMeta(
                src_abs_path=(src_root / raw.rel_path_to_v1_json).resolve(),
                zone="stage",
                data_product=raw.data_product,
                data_module=raw.data_module,
                name=raw.name,
                display_name=raw.display_name,
                v1_locators=[
                    f"/{_v1_zone_label('raw')}/{raw.data_product}/{raw.data_module}/{raw.name}",
                    f"/{_v1_zone_label('stage')}/{raw.data_product}/{raw.data_module}/{raw.name}",
                ],
                v2_rel_path=v2_rel_path,
                entity_id=0,
                raw_key=raw.key,
                v1={"type": "stage", "entity": raw.v1.get("entity"), "function": raw.v1.get("function")},
            )
        )

    zone_base = {"stage": 1000, "core": 2000, "curated": 3000, "consumer": 4000}
    for zone in ["stage", "core", "curated", "consumer"]:
        group = sorted([e for e in v1_entities if e.zone == zone], key=lambda e: e.v2_rel_path)
        for idx, e in enumerate(group):
            e.entity_id = zone_base[zone] + idx

    v1_locator_to_new_id: dict[str, int] = {}
    for e in v1_entities:
        for loc in e.v1_locators:
            if loc in v1_locator_to_new_id:
                warnings.append(f"Model: duplicate V1 locator '{loc}' detected; references may be ambiguous.")
                continue
            v1_locator_to_new_id[loc] = e.entity_id

    prop_display_names: dict[str, str] = {}
    property_values_by_prop: dict[str, set[str]] = {}

    def get_param_prop_name(original_name: str) -> str:
        base = f"param_{_slugify(original_name) or 'param'}"
        existing = prop_display_names.get(base)
        if not existing:
            prop_display_names[base] = original_name
            return base
        if existing == original_name:
            return base
        n = 2
        while f"{base}_{n}" in prop_display_names:
            n += 1
        nxt = f"{base}_{n}"
        warnings.append(f"Properties: parameter name collision for '{original_name}' -> '{base}'; using '{nxt}'.")
        prop_display_names[nxt] = original_name
        return nxt

    def add_property_value(prop: str, value: str) -> None:
        property_values_by_prop.setdefault(prop, set()).add(value)

    def build_property_refs_from_tags(tags: Any, out: list[dict[str, str]]) -> None:
        if not isinstance(tags, list):
            return
        for t in tags:
            if not isinstance(t, str) or not t.strip():
                continue
            tag = t.strip()
            out.append({"property": "tags", "value": tag})
            add_property_value("tags", tag)

    def build_property_refs_from_parameters(params: Any, out: list[dict[str, str]], context: str) -> None:
        if not isinstance(params, list):
            return
        for p in params:
            if not isinstance(p, dict):
                continue
            name_raw = p.get("name")
            name = name_raw if isinstance(name_raw, str) else ""
            if not name.strip():
                continue
            prop_name = get_param_prop_name(name.strip())
            raw_value = p.get("value", None)
            if raw_value is None:
                raw_value = p.get("custom", None)
            val_str = _stringify_value(raw_value, warnings, f"{context}: parameter '{name}'")
            if not val_str or not val_str.strip():
                continue
            out.append({"property": prop_name, "value": val_str})
            add_property_value(prop_name, val_str)

    def to_source_data_type(raw_attr: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": raw_attr.get("type"),
            "nullable": bool(raw_attr.get("nullable")) if raw_attr.get("nullable") is not None else True,
        }
        char_len_raw = raw_attr.get("charLength")
        prec_raw = raw_attr.get("precision")
        scale_raw = raw_attr.get("scale")
        if isinstance(char_len_raw, (int, float)) and float(char_len_raw) > 0:
            out["charLen"] = int(char_len_raw)
        if isinstance(prec_raw, (int, float)) and float(prec_raw) > 0:
            out["precision"] = int(prec_raw)
        if isinstance(scale_raw, (int, float)) and float(scale_raw) >= 0:
            out["scale"] = int(scale_raw)
        return out

    def convert_entity(meta: _V1EntityMeta) -> dict[str, Any]:
        ent_raw = meta.v1.get("entity")
        ent = ent_raw if isinstance(ent_raw, dict) else {}

        entity_kept = {
            "dataModule",
            "dataProduct",
            "name",
            "displayName",
            "purpose",
            "explanation",
            "parameters",
            "tags",
            "attribute",
            "relationship",
        }
        _warn_dropped_fields(warnings, meta.v2_rel_path, ent, entity_kept)

        entity_properties: list[dict[str, str]] = []
        build_property_refs_from_tags(ent.get("tags"), entity_properties)
        build_property_refs_from_parameters(ent.get("parameters"), entity_properties, meta.v2_rel_path)

        v1_attrs_raw = ent.get("attribute")
        v1_attrs = v1_attrs_raw if isinstance(v1_attrs_raw, list) else []
        attrs_out: list[dict[str, Any]] = []
        if not v1_attrs:
            warnings.append(f"{meta.v2_rel_path}: entity has no attributes; generated placeholder attribute.")
            attrs_out.append(
                {
                    "ordinalNumber": 1,
                    "name": "id",
                    "description": "",
                    "attributeType": "ID",
                    "dataType": {"type": "string", "nullable": False},
                    "dateAdded": _to_iso_now(),
                }
            )
        else:
            for idx, a in enumerate(v1_attrs):
                if not isinstance(a, dict):
                    continue
                name_raw = a.get("name")
                attribute_type_raw = a.get("attributeType")
                name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else f"attr_{idx+1}"
                attribute_type = (
                    attribute_type_raw.strip()
                    if isinstance(attribute_type_raw, str) and attribute_type_raw.strip()
                    else "ID"
                )
                v1_type = a.get("dataType") if a.get("dataType") is not None else a.get("type")
                dt: dict[str, Any] = {
                    "type": _normalize_internal_type(v1_type),
                    "nullable": bool(a.get("nullable")) if isinstance(a.get("nullable"), bool) else True,
                }
                char_len = a.get("charLength") if a.get("charLength") is not None else a.get("charLen")
                if isinstance(char_len, (int, float)) and float(char_len) > 0:
                    dt["charLen"] = int(char_len)
                prec_raw = a.get("precision")
                if isinstance(prec_raw, (int, float)) and float(prec_raw) > 0:
                    dt["precision"] = int(prec_raw)
                scale_raw = a.get("scale")
                if isinstance(scale_raw, (int, float)) and float(scale_raw) >= 0:
                    dt["scale"] = int(scale_raw)

                attribute_properties: list[dict[str, str]] = []
                build_property_refs_from_tags(a.get("tags"), attribute_properties)
                build_property_refs_from_parameters(a.get("parameter"), attribute_properties, f"{meta.v2_rel_path}:{name}")

                date_modified = _to_datetime_iso(a.get("dateModified"))
                attrs_out.append(
                    {
                        "ordinalNumber": idx + 1,
                        "name": name,
                        "displayName": a.get("displayName") if isinstance(a.get("displayName"), str) else None,
                        "description": a.get("purpose") if isinstance(a.get("purpose"), str) else (a.get("explanation") if isinstance(a.get("explanation"), str) else ""),
                        "attributeType": attribute_type,
                        "dataType": dt,
                        "isBusinessKey": bool(a.get("businessKeyNo")) if isinstance(a.get("businessKeyNo"), (int, float)) else False,
                        "history": _normalize_v2_history(a.get("history")),
                        "refactorNames": a.get("refactorNames") if isinstance(a.get("refactorNames"), list) else None,
                        "dateModified": date_modified,
                        "dateAdded": _to_iso_now(),
                        "properties": _dedupe_property_refs(attribute_properties) if attribute_properties else None,
                    }
                )

        sources_out: list[dict[str, Any]] = []
        transformations_out: list[dict[str, Any]] = []

        if meta.zone == "stage":
            stage_fn_raw = meta.v1.get("function")
            stage_fn = stage_fn_raw if isinstance(stage_fn_raw, dict) else {}
            raw = raw_by_key.get(meta.raw_key) if meta.raw_key else None
            data_source = None
            source_location = None
            if raw and raw.function:
                data_source = raw.function.get("dataSource") or data_source
                source_location = raw.function.get("sourceLocation") or source_location
            stage_ds_raw = stage_fn.get("dataSource")
            if isinstance(stage_ds_raw, str) and stage_ds_raw.strip():
                data_source = stage_ds_raw.strip()
            stage_sl_raw = stage_fn.get("sourceLocation")
            if isinstance(stage_sl_raw, str) and stage_sl_raw.strip():
                source_location = stage_sl_raw.strip()

            raw_attr_by_name: dict[str, dict[str, Any]] = {}
            if raw and raw.attributes:
                for ra in raw.attributes:
                    ra_name = ra.get("name")
                    if isinstance(ra_name, str):
                        raw_attr_by_name[ra_name] = ra

            mapping_out: list[dict[str, Any]] = []
            v1_map_raw = stage_fn.get("attributeMapping")
            v1_map = v1_map_raw if isinstance(v1_map_raw, list) else None
            if v1_map:
                for m in v1_map:
                    if not isinstance(m, dict):
                        continue
                    source_name_raw = m.get("source")
                    target_name_raw = m.get("target")
                    source_name = source_name_raw if isinstance(source_name_raw, str) else ""
                    target_name = target_name_raw if isinstance(target_name_raw, str) else ""
                    if not source_name.strip() or not target_name.strip():
                        continue
                    row: dict[str, Any] = {"sourceName": source_name.strip(), "targetName": target_name.strip()}
                    raw_attr = raw_attr_by_name.get(row["sourceName"])
                    if raw_attr:
                        row["sourceDataType"] = to_source_data_type(raw_attr)
                    mapping_out.append(row)
            else:
                for a in attrs_out:
                    n_raw = a.get("name")
                    n = n_raw if isinstance(n_raw, str) else ""
                    if not n.strip():
                        continue
                    row: dict[str, Any] = {"sourceName": n, "targetName": n}
                    raw_attr = raw_attr_by_name.get(n)
                    if raw_attr:
                        row["sourceDataType"] = to_source_data_type(raw_attr)
                    mapping_out.append(row)

            final_data_source = data_source or "unknown"
            final_source_location = source_location or "unknown"
            if not data_source or not source_location:
                warnings.append(
                    f"{meta.v2_rel_path}: Stage entity is missing dataSource/sourceLocation; using '{final_data_source}' / '{final_source_location}'."
                )
            sources_out.append(
                {
                    "dataSource": final_data_source,
                    "sourceLocation": final_source_location,
                    "mapping": mapping_out if mapping_out else None,
                }
            )
        elif meta.zone == "curated":
            v1_fns_raw = meta.v1.get("function")
            v1_fns = v1_fns_raw if isinstance(v1_fns_raw, list) else []
            if v1_fns:
                warnings.append(f"{meta.v2_rel_path}: curated function metadata (merge_type/frequency/etc.) is not migrated.")
            for idx, fn in enumerate(v1_fns):
                if not isinstance(fn, dict):
                    continue
                fn_name_raw = fn.get("name")
                name = fn_name_raw.strip() if isinstance(fn_name_raw, str) else ""
                if not name:
                    continue
                transformations_out.append(
                    {"stepNo": idx + 1, "kind": "function", "name": name, "function": {"source": f"{meta.name}/{name}.py"}}
                )
            locator_set: set[str] = set()
            for fn in v1_fns:
                if not isinstance(fn, dict):
                    continue
                sources_raw = fn.get("source")
                sources = sources_raw if isinstance(sources_raw, list) else []
                for s in sources:
                    if not isinstance(s, dict):
                        continue
                    dm8l_raw = s.get("dm8l")
                    dm8l = dm8l_raw.strip() if isinstance(dm8l_raw, str) else ""
                    if dm8l.startswith("/"):
                        locator_set.add(dm8l)
            for loc in sorted(locator_set):
                target_id = v1_locator_to_new_id.get(loc)
                if target_id is None:
                    warnings.append(f"{meta.v2_rel_path}: curated source '{loc}' is unresolved; skipped.")
                    continue
                sources_out.append({"sourceLocation": target_id})
        else:
            fn_raw = meta.v1.get("function")
            fn = fn_raw if isinstance(fn_raw, dict) else {}
            v1_sources_raw = fn.get("source")
            v1_sources = v1_sources_raw if isinstance(v1_sources_raw, list) else []
            for s in v1_sources:
                if not isinstance(s, dict):
                    continue
                dm8l_raw = s.get("dm8l")
                dm8l = dm8l_raw if isinstance(dm8l_raw, str) else ""
                if not dm8l.strip():
                    continue
                dm8l = dm8l.strip()
                if dm8l == "#":
                    warnings.append(f"{meta.v2_rel_path}: dropped external source '#'; no V2 mapping without dataSource.")
                    continue
                if not dm8l.startswith("/"):
                    warnings.append(f"{meta.v2_rel_path}: dropped unrecognized source '{dm8l}'.")
                    continue
                target_id = v1_locator_to_new_id.get(dm8l)
                mapping_out2: list[dict[str, str]] = []
                mapping_raw = s.get("mapping")
                mapping_list = mapping_raw if isinstance(mapping_raw, list) else []
                for m in mapping_list:
                    if not isinstance(m, dict):
                        continue
                    if isinstance(m.get("name"), str) and isinstance(m.get("sourceName"), str):
                        mapping_out2.append({"targetName": m["name"], "sourceName": m["sourceName"]})
                sources_out.append(
                    {
                        "sourceLocation": target_id if target_id is not None else dm8l,
                        "mapping": mapping_out2 if mapping_out2 else None,
                    }
                )

        rel_out: list[dict[str, Any]] = []
        v1_rels_raw = ent.get("relationship")
        v1_rels = v1_rels_raw if isinstance(v1_rels_raw, list) else []
        for r in v1_rels:
            if not isinstance(r, dict):
                continue
            target = r.get("dm8lKey") if isinstance(r.get("dm8lKey"), str) else ""
            target_id = v1_locator_to_new_id.get(target) if target else None
            fields_raw = r.get("fields")
            fields = fields_raw if isinstance(fields_raw, list) else []
            attrs = []
            for f in fields:
                if not isinstance(f, dict):
                    continue
                source_name = f.get("dm8lAttr") if isinstance(f.get("dm8lAttr"), str) else ""
                target_name = f.get("dm8lKeyAttr") if isinstance(f.get("dm8lKeyAttr"), str) else ""
                if source_name and target_name:
                    attrs.append({"sourceName": source_name, "targetName": target_name})
            if target_id is None:
                warnings.append(f"{meta.v2_rel_path}: dropped relationship to '{target}' (unresolved target).")
                continue
            if not attrs:
                warnings.append(f"{meta.v2_rel_path}: dropped relationship to '{target}' (no mappable fields).")
                continue
            rel_out.append({"targetLocation": target_id, "attributes": attrs})

        return {
            "id": meta.entity_id,
            "name": meta.name,
            "displayName": meta.display_name or meta.name,
            "description": ent.get("purpose") if isinstance(ent.get("purpose"), str) else (ent.get("explanation") if isinstance(ent.get("explanation"), str) else ""),
            "parameters": [],
            "properties": _dedupe_property_refs(entity_properties) if entity_properties else None,
            "attributes": attrs_out,
            "sources": sources_out,
            "relationships": rel_out,
            "transformations": transformations_out,
        }

    entities_sorted = sorted(v1_entities, key=lambda e: e.v2_rel_path)
    for meta in entities_sorted:
        out = convert_entity(meta)
        abs_out = out_root / meta.v2_rel_path
        _write_json(abs_out, out)
        written_files += 1
        migrated_model_entities += 1

        if meta.zone == "curated":
            v1_fns_raw = meta.v1.get("function")
            v1_fns = v1_fns_raw if isinstance(v1_fns_raw, list) else []
            v1_entity_dir = meta.src_abs_path.parent if meta.src_abs_path else None
            v2_entity_dir = abs_out.parent

            def is_safe_fn_name(n: str) -> bool:
                return bool(n) and "/" not in n and "\\" not in n and ".." not in n and "\0" not in n and n.strip() == n

            for fn in v1_fns:
                if not isinstance(fn, dict):
                    continue
                fn_name_raw = fn.get("name")
                fn_name = fn_name_raw.strip() if isinstance(fn_name_raw, str) else ""
                if not fn_name:
                    continue
                if not is_safe_fn_name(fn_name):
                    warnings.append(f"{meta.v2_rel_path}: invalid function name '{fn_name}'; script copy skipped.")
                    continue
                v2_sidecar_dir = v2_entity_dir / meta.name
                v2_script_abs = v2_sidecar_dir / f"{fn_name}.py"
                v2_script_abs.parent.mkdir(parents=True, exist_ok=True)

                v1_script_abs = (v1_entity_dir / meta.name / f"{fn_name}.py") if v1_entity_dir else None
                try:
                    if not v1_script_abs:
                        raise FileNotFoundError("missing V1 entity path")
                    content = v1_script_abs.read_text(encoding="utf-8")
                    v2_script_abs.write_text(content, encoding="utf-8")
                except Exception:
                    warnings.append(
                        f"Missing V1 script for {meta.data_product}::{meta.data_module}::{meta.name} function {fn_name}: expected {str(v1_script_abs) if v1_script_abs else '<unknown>'}"
                    )

    properties_out = [{"name": "tags", "displayName": "Tags"}]
    for prop, display in sorted(prop_display_names.items(), key=lambda kv: kv[0]):
        properties_out.append({"name": prop, "displayName": display})

    property_values_out: list[dict[str, str]] = []
    all_props = {"tags", *prop_display_names.keys()}
    for prop in all_props:
        values = property_values_by_prop.get(prop)
        if not values:
            continue
        for v in values:
            if not v or not v.strip():
                continue
            property_values_out.append({"name": v, "displayName": v, "property": prop})
    property_values_out.sort(key=lambda row: f"{row.get('property','')}::{row.get('name','')}")

    out_properties_file = {"type": "properties", "properties": properties_out}
    out_property_values_file = {"type": "propertyValues", "propertyValues": property_values_out}

    def write_base(name: str, content: Any) -> None:
        nonlocal written_files
        rel = f"Base/{name}.json"
        _write_json(out_root / rel, content)
        migrated_base_files.append(rel)
        written_files += 1

    write_base("AttributeTypes", out_attribute_types)
    write_base("DataTypes", out_data_types)
    write_base("DataSourceTypes", out_data_source_types)
    write_base("DataSources", out_data_sources)
    write_base("DataProducts", out_data_products)
    write_base("Zones", out_zones)
    write_base("Properties", out_properties_file)
    write_base("PropertyValues", out_property_values_file)

    generate_path = v1_solution_raw.get("generatePath")
    diagram_path = v1_solution_raw.get("diagramPath")
    output_path = v1_solution_raw.get("outputPath")
    if copy_generate and isinstance(generate_path, str) and generate_path.strip():
        _safe_cp(src_root / generate_path, out_root / "Generate", copied_paths, warnings, "Generate")
    if copy_diagram and isinstance(diagram_path, str) and diagram_path.strip():
        _safe_cp(src_root / diagram_path, out_root / "Diagram", copied_paths, warnings, "Diagram")
    if copy_output and isinstance(output_path, str) and output_path.strip():
        _safe_cp(src_root / output_path, out_root / "Output", copied_paths, warnings, "Output")

    generator_targets: list[dict[str, Any]] = []
    if isinstance(generate_path, str) and generate_path.strip():
        try:
            gen_abs = src_root / generate_path
            for e in gen_abs.iterdir():
                if not e.is_dir():
                    continue
                if e.name.startswith(".") or e.name.startswith("__"):
                    continue
                generator_targets.append(
                    {"name": e.name, "isDefault": False, "sourcePath": f"Generate/{e.name}", "outputPath": f"Output/{e.name}/generated"}
                )
        except Exception as e:
            warnings.append(f"Generator: failed to scan V1 generatePath ({e}); using fallback target.")
    if not generator_targets:
        generator_targets = [{"name": "default", "isDefault": True, "sourcePath": "Generate/default", "outputPath": "Output/default/generated"}]
    else:
        generator_targets[0]["isDefault"] = True

    for t in generator_targets:
        (out_root / t["outputPath"]).mkdir(parents=True, exist_ok=True)

    v2_solution: dict[str, Any] = {
        "schemaVersion": "2.0.0",
        "basePath": "Base",
        "modelPath": "Model",
        "generatorTargets": generator_targets,
    }
    if copy_diagram:
        v2_solution["diagramPath"] = "Diagram"

    target_solution_path = out_root / f"{solution_name}.dm8s"
    _write_json(target_solution_path, v2_solution)
    written_files += 1

    try:
        regenerate_index(str(target_solution_path))
        written_files += 1
    except Exception as e:
        warnings.append(f"index.json: failed to generate ({e})")

    finished_at = _to_iso_now()
    duration_ms = int(
        (datetime.fromisoformat(finished_at.replace("Z", "+00:00")) - datetime.fromisoformat(started_at.replace("Z", "+00:00"))).total_seconds()
        * 1000
    )

    return {
        "targetSolutionPath": str(target_solution_path),
        "report": {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationMs": duration_ms,
            "writtenFiles": written_files,
            "migratedBaseFiles": migrated_base_files,
            "migratedModelEntities": migrated_model_entities,
            "copiedPaths": copied_paths,
            "warnings": warnings,
            "errors": errors,
        },
    }
