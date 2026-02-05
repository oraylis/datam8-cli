from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from datam8.core.errors import Datam8ValidationError
from datam8.core.jobs.manager import JobManager

router = APIRouter()


def _jm(request: Request) -> JobManager:
    jm = getattr(request.app.state, "job_manager", None)
    if not isinstance(jm, JobManager):
        raise Datam8ValidationError(message="Job system is not available.", details=None)
    return jm


class CreateJobBody(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/jobs")
async def create_job(body: CreateJobBody, request: Request) -> dict[str, Any]:
    job = _jm(request).create_job(type=body.type, params=body.params)
    return {"jobId": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    jm = _jm(request)
    job = jm.get_job(job_id)
    return jm.to_public_job(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    jm = _jm(request)
    job = jm.cancel_job(job_id)
    return jm.to_public_job(job)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    jm = _jm(request)

    async def event_stream():
        q, initial, close = jm.open_subscription(job_id)
        try:
            for ev in initial:
                yield jm.format_sse(ev)
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield jm.format_sse(ev)

                # Close after terminal status.
                if ev.type == "status":
                    job = jm.get_job(job_id)
                    if job.status in {"succeeded", "failed", "canceled"}:
                        return
        finally:
            close()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
