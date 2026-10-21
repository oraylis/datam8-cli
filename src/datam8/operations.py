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

"""Local model operations shared by individual CLI commands and ordered batches."""

from __future__ import annotations

import copy
import json
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from datam8 import config, errors, factory, functions, source
from datam8.model import EntityWrapper
from datam8.model.model import class_from_type
from datam8.plugins.navigation import normalize_source_item
from datam8_model import base as b
from datam8_model import model as m


class Operation(BaseModel):
    """The same operation arguments are used by commands and batch input."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)
    op: Literal[
        "create",
        "update",
        "delete",
        "clone",
        "rename",
        "move",
        "sources.import",
        "sources.refresh",
        "functions.create",
        "functions.update",
        "functions.delete",
        "functions.move",
        "secrets.set",
        "generate",
    ]
    locator: str | None = None
    at: list[str | int | dict[str, Any]] | None = None
    data: Any = None
    source_file: str | None = Field(default=None, alias="sourceFile")
    new_locator: str | None = Field(default=None, alias="newLocator")
    new_name: str | None = Field(default=None, alias="newName")
    data_source: str | None = Field(default=None, alias="dataSource")
    source_location: str | None = Field(default=None, alias="sourceLocation")
    mode: Literal["complete", "sources-only"] = "complete"
    step_no: int | None = Field(default=None, alias="stepNo", ge=1)
    name: str | None = None
    source_code: str | None = Field(default=None, alias="sourceCode")
    new_path: str | None = Field(default=None, alias="newPath")
    path: str | None = None
    value: str | None = None
    force: bool = False
    target: str | None = None
    payloads: list[str] = Field(default_factory=list)
    clean_output: bool = Field(default=False, alias="cleanOutput")
    lazy: bool = False

    @model_validator(mode="after")
    def check_arguments(self):
        required = {
            "create": {"locator", "data"},
            "update": {"locator", "data"},
            "delete": {"locator"},
            "clone": {"locator", "new_locator"},
            "rename": {"locator", "new_name"},
            "move": {"locator", "new_locator"},
            "sources.import": {"locator", "data_source", "source_location"},
            "sources.refresh": {"locator"},
            "functions.create": {"locator", "data", "source_code"},
            "functions.update": {"locator", "source_code"},
            "functions.delete": {"locator"},
            "functions.move": {"locator", "new_path"},
            "secrets.set": {"path", "value"},
            "generate": set(),
        }[self.op]
        optional = {
            "create": {"at", "source_file"},
            "update": {"at"},
            "delete": {"at"},
            "move": {"force"},
            "sources.refresh": {"mode"},
            "functions.update": {"step_no", "name"},
            "functions.delete": {"step_no", "name"},
            "functions.move": {"step_no", "name", "force"},
            "secrets.set": {"force"},
            "generate": {"target", "payloads", "clean_output", "lazy"},
        }.get(self.op, set())
        for field in required:
            if field not in self.model_fields_set or (
                field != "data" and getattr(self, field) is None
            ):
                raise ValueError(f"{self.op} requires {field}")
            value = getattr(self, field)
            if (
                field not in ("data", "value", "source_code")
                and isinstance(value, str)
                and not value.strip()
            ):
                raise ValueError(f"{field} cannot be empty")
        unexpected = self.model_fields_set - required - optional - {"op"}
        if unexpected:
            raise ValueError(
                f"Unsupported arguments for {self.op}: {', '.join(sorted(unexpected))}"
            )
        if self.at and self.source_file is not None:
            raise ValueError("sourceFile selects an entity collection, not a nested list")
        if self.op in {"functions.update", "functions.delete", "functions.move"}:
            if (self.step_no is None) == (self.name is None):
                raise ValueError("Provide exactly one of stepNo or name")
        for segment in self.at or []:
            if isinstance(segment, dict) and not segment:
                raise ValueError("A list selector must contain at least one key")
        return self


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[Operation]


def select_key(value: Any, segment: str | int | dict[str, Any]) -> str | int:
    if isinstance(segment, dict):
        if not isinstance(value, list):
            raise errors.Datam8ValidationError(message="A key selector requires a list")
        matches = [
            i
            for i, item in enumerate(value)
            if isinstance(item, dict)
            and all(k in item and cast(dict[str, Any], item)[k] == v for k, v in segment.items())
        ]
        if len(matches) != 1:
            raise errors.Datam8ValidationError(
                message=f"Selector must match exactly one item; found {len(matches)}",
                details={"selector": segment},
            )
        return matches[0]
    if isinstance(value, list) and isinstance(segment, int) and 0 <= segment < len(value):
        return segment
    if isinstance(value, dict) and isinstance(segment, str) and segment in value:
        return segment
    raise errors.Datam8NotFoundError(message=f"JSON path segment not found: {segment}")


def select(value: Any, at: list | None) -> Any:
    for segment in at or []:
        value = value[select_key(value, segment)]
    return value


def relative_file(path: Path) -> str:
    return path.resolve().relative_to(config.solution_folder_path.resolve()).as_posix()


def schema_for(entity_type: str, at: list | None = None) -> dict:
    entity_class = class_from_type(b.EntityType(entity_type))
    schema = entity_class.model_json_schema(by_alias=True)
    definitions = schema.get("$defs", {})
    current = schema
    for field in at or []:
        while "$ref" in current:
            current = definitions[current["$ref"].rsplit("/", 1)[-1]]
        if "anyOf" in current:
            choices = [c for c in current["anyOf"] if c.get("type") != "null"]
            if len(choices) != 1:
                raise errors.Datam8ValidationError(message="Select a field before a schema union")
            current = choices[0]
            if "$ref" in current:
                current = definitions[current["$ref"].rsplit("/", 1)[-1]]
        if current.get("type") == "array":
            current = current["items"]
            if "$ref" in current:
                current = definitions[current["$ref"].rsplit("/", 1)[-1]]
        if not isinstance(field, str) or field not in current.get("properties", {}):
            raise errors.Datam8NotFoundError(message=f"Schema field not found: {field}")
        current = current["properties"][field]
    result = copy.deepcopy(current)
    needed = {}

    def references(node):
        if isinstance(node, dict):
            ref = node.get("$ref", "").removeprefix("#/$defs/")
            if ref in definitions and ref not in needed:
                needed[ref] = definitions[ref]
                references(definitions[ref])
            for key, child in node.items():
                if key != "$defs":
                    references(child)
        elif isinstance(node, list):
            for child in node:
                references(child)

    references(result)
    result.pop("$defs", None)
    if needed:
        result["$defs"] = needed
    return result


class ModelSession:
    def __init__(self, solution: Path):
        config.set_solution(solution)
        config.lazy = True
        self.model = factory.create_model()
        factory._plugin_manager = None

    def show(self, selector: str, by="locator", at=None, fields: str | None = None):
        from datam8 import opts

        wrapper = self.model.get_entity_by_selector(selector, by=opts.Selectors(by))
        data = select(wrapper.entity.model_dump(mode="json", by_alias=True, exclude_unset=True), at)
        if fields:
            if not isinstance(data, dict):
                raise errors.Datam8ValidationError(message="--fields requires an object")
            data = {key: data[key] for key in fields.split(",") if key in data}
        return {
            "item": {
                "locator": str(wrapper.locator),
                "sourceFile": relative_file(wrapper.source_file),
                "data": data,
            }
        }

    def list(
        self, locator="modelEntities", fields=None, limit=100, offset=0, property_locator=None
    ):
        wrappers = (
            self.model.get_entities_by_property(property_locator, locator)
            if property_locator
            else self.model.get_entities(locator)
        )
        wrappers = sorted(wrappers, key=lambda w: str(w.locator))
        items = []
        for wrapper in wrappers[offset : offset + limit if limit else None]:
            row = {
                "locator": str(wrapper.locator),
                "sourceFile": relative_file(wrapper.source_file),
            }
            if hasattr(wrapper.entity, "id"):
                row["id"] = wrapper.entity.id
            if fields:
                data = wrapper.entity.model_dump(mode="json", by_alias=True, exclude_unset=True)
                row.update({key: data[key] for key in fields.split(",") if key in data})
            items.append(row)
        return {"count": len(wrappers), "offset": offset, "items": items}

    def persist(self, files=()):
        changed, deleted = self.model.get_unsaved_entities()
        paths = {
            relative_file(w.source_file)
            for w in self.model.get_entity_iterator()
            if w.has_changed or w.is_deleted
        }
        paths.update(relative_file(p) for p in files)
        self.model.save()
        factory._plugin_manager = None
        return {
            "changed": sorted(map(str, changed)),
            "deleted": sorted(map(str, deleted)),
            "files": sorted(paths),
        }

    def execute(self, operation: Operation) -> dict:
        op = operation
        created = None
        locator = cast(str, op.locator)
        if op.op not in ("secrets.set", "generate"):
            assert locator is not None
        if op.op.startswith("functions."):
            return self.function_operation(op)
        if op.op == "sources.import":
            assert op.data_source is not None and op.source_location is not None
            self.require_new(locator)
            created = source.import_from_source(
                op.data_source, op.source_location, locator, model=self.model
            )
        elif op.op == "sources.refresh":
            wrapper, diff = source.compare_entity_with_source(
                locator, model=self.model, mode=op.mode
            )
            if diff:
                self.model.modelEntities[wrapper.locator].update(**wrapper.entity.model_dump())
        elif op.op == "secrets.set":
            from datam8.secrets import SecretResolver

            assert op.path is not None and op.value is not None
            SecretResolver().set_secret(op.path, op.value, force=op.force)
            return {"path": op.path, "stored": True}
        elif op.op == "generate":
            from datam8 import generate, opts

            if not op.lazy:
                self.model.resolve()
            generate.payload_functions.clear()
            target = op.target or self.model.get_generator_default_target().name
            try:
                generate.generate_output(
                    self.model,
                    target=target or opts.default_target,
                    payloads=op.payloads,
                    clean_output=op.clean_output,
                    generate_all=False,
                )
            except SystemExit as exc:
                raise RuntimeError("Generation failed; see stderr") from exc
            return {
                "target": target,
                "outputPath": self.model.get_generator_target(target).outputPath.as_posix(),
            }
        elif op.at:
            wrapper = self.model.get_entity_by_locator(locator)
            original = wrapper.entity.model_dump(mode="json", by_alias=True, exclude_unset=True)
            data = copy.deepcopy(original)
            if op.op == "create":
                parent = select(data, op.at[:-1])
                field = op.at[-1]
                if (
                    isinstance(parent, dict)
                    and isinstance(field, str)
                    and parent.get(field) is None
                ):
                    parent[field] = []
                target = select(data, op.at)
                if not isinstance(target, list):
                    raise errors.Datam8ValidationError(message="create --at requires a list")
                target.append(op.data)
            else:
                parent = select(data, op.at[:-1])
                key = select_key(parent, op.at[-1])
                if op.op == "delete":
                    del parent[key]
                elif isinstance(parent[key], dict) and isinstance(op.data, dict):
                    parent[key].update(op.data)
                else:
                    parent[key] = op.data
            self.update_wrapper(wrapper, original, data)
        elif op.op == "create":
            self.require_new(locator)
            if not isinstance(op.data, dict):
                raise errors.Datam8ValidationError(message="Entity creation requires a JSON object")
            created = self.model.add_entity(
                locator, copy.deepcopy(op.data), source_file=op.source_file
            )
        elif op.op == "update":
            if not isinstance(op.data, dict):
                raise errors.Datam8ValidationError(message="Entity update requires a JSON object")
            wrapper = self.model.get_entity_by_locator(locator)
            original = wrapper.entity.model_dump(mode="json", by_alias=True, exclude_unset=True)
            self.update_wrapper(wrapper, original, {**original, **op.data})
        elif op.op == "delete":
            self.model.delete_entities(locator)
        elif op.op == "clone":
            assert op.new_locator is not None
            self.require_new(op.new_locator)
            created = self.model.clone_entity(locator, op.new_locator)
        elif op.op == "rename":
            assert op.new_name is not None
            self.model.rename_entity(locator, op.new_name)
        elif op.op == "move":
            assert op.new_locator is not None
            self.model.move_entities(locator, op.new_locator, force=op.force)
        result = self.persist()
        if created is not None and isinstance(created.entity, m.ModelEntity):
            result["item"] = {"locator": str(created.locator), "id": created.entity.id}
        return result

    def require_new(self, locator):
        if self.model.has_locator(locator):
            raise errors.Datam8ValidationError(message=f"Entity already exists: {locator}")

    def update_wrapper(self, wrapper, original, data):
        for field in ("id", "name", "path", "property"):
            if original.get(field) != data.get(field) and field in original:
                raise errors.Datam8ValidationError(
                    message=f"Use rename/move to change entity identity field: {field}"
                )
        validated = type(wrapper.entity).model_validate(data)
        wrapper.update(**validated.model_dump())
        wrapper.resolved = False
        self.model.resolve_wrapper(wrapper)

    def source_info(self, action, data_source, location=None, limit=10):
        plugin = factory.get_plugin_for_data_source(data_source, model=self.model)
        if action == "capabilities":
            return {"item": plugin.get_source_capabilities()}
        if action == "test-connection":
            result = plugin.test_connection()
            if isinstance(result, Exception):
                raise result
            return {"item": {"connected": True}}
        if action == "list":
            items = [
                normalize_source_item(row, location)
                for row in plugin.list_source(location).to_dicts()
            ]
            return {"count": len(items), "items": items}
        if action == "preview":
            assert location is not None
            if not plugin.get_source_capabilities().get("previewData", False):
                raise errors.Datam8ValidationError(message="Source does not support preview")
            frame = next(
                plugin.preview_data(location, limit=limit).collect_batches(chunk_size=limit), None
            )
            items = [] if frame is None else frame.head(limit).to_dicts()
            return {"count": len(items), "items": items}
        if action == "metadata":
            assert location is not None
            metadata = plugin.get_table_metadata(location)
            items = [field.model_dump(mode="json") for field in metadata.iter_source_fields()]
            return {
                "count": len(items),
                "items": items,
                "object": metadata.source_object.model_dump(mode="json"),
                "sourceLocation": location,
                "sourceOverride": metadata.source_object.sourceOverride,
            }
        if action == "import-description":
            assert location is not None
            definitions = plugin.get_sources(location)
            entity = (
                None
                if definitions is None
                else source.read_from_data_source(
                    data_source, location, model=self.model, source_definitions=definitions
                )
            )
            return {
                "item": None
                if entity is None
                else entity.model_dump(mode="json", exclude_unset=True)
            }
        raise ValueError(f"Unknown source action: {action}")

    def compare(self, locator, mode="complete"):
        wrapper, diff = source.compare_entity_with_source(locator, model=self.model, mode=mode)
        return {
            "item": {
                "locator": str(wrapper.locator),
                "hasChanges": bool(diff),
                "diff": json.loads(diff.to_json()),
            }
        }

    def function_source(self, wrapper, transformation):
        if transformation.kind != m.TransformationKind.FUNCTION or transformation.function is None:
            raise errors.Datam8ValidationError(message="Transformation is not function-backed")
        name = transformation.function.source
        parts = name.replace("\\", "/").split("/")
        if (
            PureWindowsPath(name).drive
            or Path(name).is_absolute()
            or any(p in ("", ".", "..") for p in parts)
        ):
            raise errors.Datam8ValidationError(
                message="Function source must be relative to its entity directory"
            )
        path = functions._build_source_file_path(wrapper, transformation)
        if not path.is_relative_to(wrapper.source_file.parent.resolve()):
            raise errors.Datam8ValidationError(
                message="Function source escapes its entity directory"
            )
        return path

    def find_function(self, wrapper, step_no=None, name=None):
        if not isinstance(wrapper.entity, m.ModelEntity):
            raise errors.Datam8ValidationError(message="Functions require a model entity")
        matches = [
            t
            for t in wrapper.entity.transformations
            if (t.stepNo == step_no if step_no is not None else t.name == name)
        ]
        if not matches:
            raise errors.Datam8NotFoundError(
                message="Function selector must identify exactly one transformation"
            )
        if len(matches) > 1:
            raise errors.Datam8ValidationError(message="Function selector is ambiguous")
        return matches[0]

    def function_operation(self, op: Operation):
        assert op.locator is not None
        wrapper = self.model.get_entity_by_locator(op.locator)
        if not isinstance(wrapper.entity, m.ModelEntity):
            raise errors.Datam8ValidationError(message="Functions require a model entity")
        wrapper = cast(EntityWrapper[m.ModelEntity], wrapper)
        if op.op == "functions.create":
            assert op.source_code is not None
            transformation = m.ModelTransformation.model_validate(op.data)
            if any(
                t.stepNo == transformation.stepNo or t.name == transformation.name
                for t in wrapper.entity.transformations
            ):
                raise errors.Datam8ValidationError(
                    message="Transformation stepNo or name already exists"
                )
            path = self.function_source(wrapper, transformation)
            if path.exists():
                raise FileExistsError("Function source already exists")
            data = wrapper.entity.model_dump(mode="json")
            data["transformations"].append(transformation.model_dump(mode="json"))
            validated = m.ModelEntity.model_validate(data)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(op.source_code)
            try:
                wrapper.update(**validated.model_dump())
                return self.persist([path])
            except Exception:
                path.unlink(missing_ok=True)
                raise
        transformation = self.find_function(wrapper, op.step_no, op.name)
        path = self.function_source(wrapper, transformation)
        if op.op == "functions.update":
            assert op.source_code is not None
            key = op.step_no if op.step_no is not None else op.name
            assert key is not None
            functions.update_function(wrapper, key, op.source_code)
            return self.persist([path])
        if op.op == "functions.move":
            assert op.new_path is not None
            candidate = transformation.model_copy(deep=True)
            assert candidate.function is not None
            candidate.function.source = op.new_path
            destination = self.function_source(wrapper, candidate)
            functions.move_function(wrapper, transformation, destination, force=op.force)
            return self.persist([path, destination])
        remaining = [t for t in wrapper.entity.transformations if t is not transformation]
        wrapper.update(transformations=remaining)
        receipt = self.persist()
        used = any(
            self.function_source(other, t) == path
            for other in self.model.modelEntities.values()
            for t in other.entity.transformations
            if t.kind == m.TransformationKind.FUNCTION
        )
        if not used:
            path.unlink(missing_ok=True)
            receipt["files"] = sorted(set(receipt["files"]) | {relative_file(path)})
        return receipt
