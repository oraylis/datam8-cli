from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

workspace_router = APIRouter(prefix="/workspace", tags=["workspace"])


class OpenWorkspaceBody(BaseModel):
    path: Path


@workspace_router.get("")
async def get_workspace(request: Request) -> dict[str, str]:
    request.app.state.workspace.require_enabled()
    return request.app.state.workspace.describe()


@workspace_router.post("/open")
async def open_workspace(body: OpenWorkspaceBody, request: Request) -> dict[str, str]:
    return await request.app.state.workspace.open(body.path)
