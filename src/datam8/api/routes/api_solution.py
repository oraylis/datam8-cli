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

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from pydantic_core import ValidationError

from datam8 import factory, model_exceptions, parser_exceptions
from datam8.core import (
    migration_v1_to_v2 as migration_v1_to_v2_core,
)
from datam8.core import workspace_io, workspace_service
from datam8.core.errors import Datam8ValidationError
from datam8.core.solution_index import detect_solution_version

from .response_models import (
    BaseEntityResponse,
    ConfigResponse,
    FolderEntityResponse,
    MigrationResponse,
    ModelEntityResponse,
    ResolvedPathsResponse,
    SolutionFullResponse,
    SolutionInfoResponse,
    SolutionPathResponse,
    SolutionResponse,
    SolutionValidateResponse,
    VersionResponse,
)

router = APIRouter()


class MigrateV1ToV2Body(BaseModel):
    """Request body for migrating a v1 solution to v2."""

    sourceSolutionPath: str
    targetDir: str
    options: dict[str, Any] | None = None


class NewProjectTargetBody(BaseModel):
    """Request body target entry for creating a new project."""

    name: str
    isDefault: bool | None = None
    sourcePath: str | None = None
    outputPath: str | None = None
    zipField: str | None = None


class NewProjectBody(BaseModel):
    """Request body for creating a new minimal solution project."""

    solutionName: str
    projectRoot: str
    basePath: str | None = None
    modelPath: str | None = None
    target: str | None = None
    targets: list[NewProjectTargetBody] | None = None
    targetArchives: dict[str, str] | None = None


def _targets_from_body(body: NewProjectBody) -> list[dict[str, Any]]:
    if body.targets is not None:
        out: list[dict[str, Any]] = []
        for entry in body.targets:
            payload: dict[str, Any] = {"name": entry.name}
            if entry.isDefault is not None:
                payload["isDefault"] = entry.isDefault
            if entry.sourcePath is not None:
                payload["sourcePath"] = entry.sourcePath
            if entry.outputPath is not None:
                payload["outputPath"] = entry.outputPath
            out.append(payload)
        return out
    if body.target and body.target.strip():
        return [{"name": body.target.strip()}]
    return []


def _decode_target_archives(payload: dict[str, str] | None) -> dict[int, bytes] | None:
    if not payload:
        return None

    decoded: dict[int, bytes] = {}
    for raw_index, raw_archive in payload.items():
        index_text = (raw_index or "").strip()
        if not index_text or not index_text.isdigit():
            raise Datam8ValidationError(
                message="targetArchives keys must be target indices.",
                details={"index": raw_index},
            )
        archive_base64 = (raw_archive or "").strip()
        if not archive_base64:
            raise Datam8ValidationError(
                message="ZIP archive content is empty.",
                details={"index": int(index_text)},
            )
        try:
            archive_bytes = base64.b64decode(archive_base64, validate=True)
        except (binascii.Error, ValueError):
            raise Datam8ValidationError(
                message="Invalid base64 ZIP archive.",
                details={"index": int(index_text)},
            )
        if not archive_bytes:
            raise Datam8ValidationError(
                message="ZIP archive content is empty.",
                details={"index": int(index_text)},
            )
        decoded[int(index_text)] = archive_bytes
    return decoded


def _parse_content_disposition(value: str) -> tuple[str | None, str | None]:
    name_match = re.search(r'name="([^"]+)"', value)
    filename_match = re.search(r'filename="([^"]*)"', value)
    field_name = name_match.group(1) if name_match else None
    filename = filename_match.group(1) if filename_match else None
    return field_name, filename


def _parse_multipart_form(
    *,
    content_type: str,
    body: bytes,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type, flags=re.IGNORECASE)
    if not boundary_match:
        raise Datam8ValidationError(message="Multipart boundary is missing.", details=None)
    boundary = boundary_match.group(1).encode("utf-8")
    delimiter = b"--" + boundary

    fields: dict[str, str] = {}
    files: dict[str, dict[str, Any]] = {}
    for chunk in body.split(delimiter):
        part = chunk
        if not part:
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"--\r\n"):
            part = part[:-4]
        elif part.endswith(b"--"):
            part = part[:-2]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if not part or part == b"--":
            continue
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if sep != b"\r\n\r\n":
            continue

        headers: dict[str, str] = {}
        for raw_line in header_blob.decode("latin-1").split("\r\n"):
            key, _, value = raw_line.partition(":")
            if not _:
                continue
            headers[key.strip().lower()] = value.strip()

        content_disposition = headers.get("content-disposition", "")
        field_name, filename = _parse_content_disposition(content_disposition)
        if not field_name:
            continue

        if filename is not None and filename != "":
            files[field_name] = {
                "filename": filename,
                "contentType": headers.get("content-type"),
                "content": content,
            }
        else:
            fields[field_name] = content.decode("utf-8")

    return fields, files


@router.get("/config")
async def config() -> ConfigResponse:
    """Return runtime configuration metadata consumed by the frontend."""
    return ConfigResponse(mode=os.environ.get("DATAM8_MODE") or "server")


@router.get("/solution/inspect")
async def solution_inspect(path: str = Query(...)) -> VersionResponse:
    """Detect and return the solution format version."""
    return VersionResponse(version=detect_solution_version(path))


@router.post("/migration/v1-to-v2")
async def migration_v1_to_v2_route(body: MigrateV1ToV2Body) -> MigrationResponse:
    """Migrate a v1 solution into v2 structure."""
    args: dict[str, Any] = {
        "sourceSolutionPath": body.sourceSolutionPath,
        "targetDir": body.targetDir,
    }
    if body.options is not None:
        args["options"] = body.options
    return MigrationResponse.model_validate(
        migration_v1_to_v2_core.migrate_solution_v1_to_v2(args)
    )


@router.get("/solution")
async def solution(path: str | None = Query(None)) -> SolutionResponse:
    """Read and return the parsed solution with resolved paths."""
    _resolved, sol = workspace_io.read_solution(path)
    return SolutionResponse(
        solution=sol,
        resolvedPaths=ResolvedPathsResponse(base=str(sol.basePath), model=str(sol.modelPath)),
    )


@router.get("/solution/info")
async def solution_info(path: str | None = Query(None)) -> SolutionInfoResponse:
    """Return resolved solution metadata including solution path."""
    resolved, sol = workspace_io.read_solution(path)
    return SolutionInfoResponse(
        solutionPath=str(resolved.solution_file),
        solution=sol,
        resolvedPaths=ResolvedPathsResponse(base=str(sol.basePath), model=str(sol.modelPath)),
    )


@router.get(
    "/solution/full",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def solution_full(path: str | None = Query(None)) -> SolutionFullResponse:
    """Read and return the full solution with base/model entities."""
    snapshot = workspace_service.get_solution_full_snapshot(path)
    base_entities = [
        BaseEntityResponse(
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in snapshot.baseEntities
    ]
    model_entities = [
        ModelEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in snapshot.modelEntities
    ]
    folder_entities = [
        FolderEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            folderPath=entity.folderPath,
            content=entity.content,
        )
        for entity in snapshot.folderEntities
    ]
    return SolutionFullResponse(
        solution=snapshot.solution,
        baseEntities=base_entities,
        modelEntities=model_entities,
        folderEntities=folder_entities,
    )


@router.post("/solution/validate")
async def solution_validate(path: str | None = Query(None)) -> SolutionValidateResponse:
    """Validate that a solution can be resolved and parsed."""
    resolved, _sol = workspace_io.read_solution(path)
    return SolutionValidateResponse(status="ok", solutionPath=str(resolved.solution_file))


@router.post("/validate")
async def validate(path: str | None = Query(None), logLevel: str | None = Query(None)) -> SolutionValidateResponse:
    """Validate full model parsing/resolution (CLI `datam8 validate` parity)."""
    candidate = path or os.environ.get("DATAM8_SOLUTION_PATH")
    if not candidate:
        raise Datam8ValidationError(
            message="No solution specified. Use path query parameter or DATAM8_SOLUTION_PATH.",
            details=None,
        )

    try:
        resolved_solution = await run_in_threadpool(
            partial(
                factory.validate_solution_model,
                solution_path=candidate,
                log_level=logLevel,
            )
        )
    except (
        RecursionError,
        ValidationError,
        parser_exceptions.ModelParseException,
        parser_exceptions.NotSupportedModelVersion,
        model_exceptions.EntityNotFoundError,
        model_exceptions.PropertiesNotResolvedError,
    ) as err:
        raise Datam8ValidationError(
            message="Solution model validation failed.",
            details={"error": str(err)},
        )

    return SolutionValidateResponse(status="ok", solutionPath=str(resolved_solution))


@router.post("/solution/new-project")
async def solution_new_project(request: Request) -> SolutionPathResponse:
    """Create a new minimal project and return solution path."""
    content_type = (request.headers.get("content-type") or "").lower()

    body: NewProjectBody
    target_archives: dict[int, bytes] | None = None

    if "multipart/form-data" in content_type:
        form_data = None
        fallback_fields: dict[str, str] = {}
        fallback_files: dict[str, dict[str, Any]] = {}

        try:
            form_data = await request.form()
        except Exception as err:
            if "python-multipart" in str(err).lower():
                raw_body = await request.body()
                fallback_fields, fallback_files = _parse_multipart_form(content_type=content_type, body=raw_body)
            else:
                raise Datam8ValidationError(
                    message="Invalid multipart form body.",
                    details={"error": str(err)},
                )

        if form_data is not None:
            payload_value = form_data.get("payload")
            if isinstance(payload_value, str):
                payload_raw = payload_value
            elif isinstance(payload_value, (bytes, bytearray)):
                try:
                    payload_raw = bytes(payload_value).decode("utf-8")
                except UnicodeDecodeError:
                    raise Datam8ValidationError(message="Multipart payload is not valid UTF-8.", details=None)
            else:
                payload_raw = ""
        else:
            payload_raw = fallback_fields.get("payload", "")

        if not payload_raw.strip():
            raise Datam8ValidationError(message="Multipart request requires 'payload' JSON field.", details=None)
        try:
            body = NewProjectBody.model_validate_json(payload_raw)
        except ValidationError as err:
            raise Datam8ValidationError(
                message="Invalid new-project payload.",
                details={"errors": err.errors()},
            )

        if body.targets:
            target_archives = {}
            for idx, target in enumerate(body.targets):
                zip_field = (target.zipField or "").strip()
                if not zip_field:
                    continue
                if form_data is not None:
                    upload = form_data.get(zip_field)
                    if upload is None:
                        raise Datam8ValidationError(
                            message="ZIP file reference not found in multipart payload.",
                            details={"zipField": zip_field, "index": idx},
                        )
                    read_fn = getattr(upload, "read", None)
                    if read_fn is None:
                        raise Datam8ValidationError(
                            message="ZIP file reference did not contain a file upload.",
                            details={"zipField": zip_field, "index": idx},
                        )
                    archive_bytes = await read_fn()
                else:
                    upload = fallback_files.get(zip_field)
                    if upload is None:
                        raise Datam8ValidationError(
                            message="ZIP file reference not found in multipart payload.",
                            details={"zipField": zip_field, "index": idx},
                        )
                    archive_bytes = upload.get("content")
                if not archive_bytes:
                    raise Datam8ValidationError(
                        message="ZIP file is empty.",
                        details={"zipField": zip_field, "index": idx},
                    )
                target_archives[idx] = archive_bytes
    else:
        raw = await request.body()
        try:
            body = NewProjectBody.model_validate(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise Datam8ValidationError(message="Invalid JSON body.", details=None)
        except ValidationError as err:
            raise Datam8ValidationError(
                message="Invalid new-project payload.",
                details={"errors": err.errors()},
            )

    decoded_archives = _decode_target_archives(body.targetArchives)
    if decoded_archives:
        if target_archives:
            target_archives.update(decoded_archives)
        else:
            target_archives = decoded_archives

    solution_path = workspace_io.create_new_project(
        solution_name=body.solutionName,
        project_root=body.projectRoot,
        base_path=body.basePath,
        model_path=body.modelPath,
        target=body.target,
        targets=_targets_from_body(body),
        target_archives=target_archives,
    )
    return SolutionPathResponse(solutionPath=solution_path)
