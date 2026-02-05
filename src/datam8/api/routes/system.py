from __future__ import annotations

from fastapi import APIRouter

from datam8.core.version import get_version

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    return {"version": get_version()}

