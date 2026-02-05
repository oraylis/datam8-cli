from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from datam8.api.routes.jobs import router as jobs_router
from datam8.api.routes.legacy_api import router as legacy_api_router
from datam8.api.routes.system import router as system_router
from datam8.core.errors import Datam8Error, Datam8ValidationError
from datam8.core.trace import new_trace_id
from datam8.core.version import get_version


def _status_for_error(err: Datam8Error) -> int:
    if err.code in {"validation_error"}:
        return 400
    if err.code in {"not_found"}:
        return 404
    if err.code in {"conflict", "locked"}:
        return 409
    if err.code in {"auth"}:
        return 401
    if err.code in {"permission"}:
        return 403
    if err.code in {"not_implemented"}:
        return 501
    if err.exit_code == 5:
        return 502
    return 500


def _is_exempt_path(path: str) -> bool:
    return path in {"/health", "/version", "/api/health"}


def create_app(*, token: str, enable_openapi: bool = False, job_manager: Any = None) -> FastAPI:
    if enable_openapi:
        app = FastAPI(title="DataM8 API", version=get_version())
    else:
        app = FastAPI(
            title="DataM8 API",
            version=get_version(),
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )

    app.state.job_manager = job_manager

    origins_env = os.environ.get("DATAM8_CORS_ORIGINS")
    allow_origin_regex = os.environ.get("DATAM8_CORS_ORIGIN_REGEX")
    allow_origins = [o.strip() for o in (origins_env or "").split(",") if o.strip()]
    if not allow_origins:
        allow_origins = [
            "http://localhost:4320",
            "http://127.0.0.1:4320",
            "http://localhost:4321",
            "http://127.0.0.1:4321",
            "null",
        ]
    if not allow_origin_regex:
        allow_origin_regex = r"^http://(localhost|127\.0\.0\.1):\d+$"

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        request.state.trace_id = new_trace_id()
        return await call_next(request)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if _is_exempt_path(request.url.path):
            return await call_next(request)

        auth = (request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            exc = Datam8Error(
                code="auth",
                message="Missing Authorization header.",
                details=None,
                hint="Use: Authorization: Bearer <token>.",
                exit_code=7,
            )
            trace_id = getattr(request.state, "trace_id", None)
            env = exc.to_envelope(trace_id=trace_id)
            return JSONResponse(status_code=401, content=env.__dict__)
        got = auth.split(" ", 1)[1].strip()
        if not got or got != token:
            exc = Datam8Error(code="auth", message="Invalid token.", details=None, hint=None, exit_code=7)
            trace_id = getattr(request.state, "trace_id", None)
            env = exc.to_envelope(trace_id=trace_id)
            return JSONResponse(status_code=401, content=env.__dict__)

        return await call_next(request)

    # Add CORS outermost so preflight OPTIONS are handled before auth and
    # CORS headers are present on all responses (including errors).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Datam8Error)
    async def datam8_error_handler(request: Request, exc: Datam8Error):
        trace_id = getattr(request.state, "trace_id", None)
        env = exc.to_envelope(trace_id=trace_id)
        return JSONResponse(status_code=_status_for_error(exc), content=env.__dict__)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", None)
        err = Datam8ValidationError(message="Invalid request.", details={"errors": exc.errors()})
        env = err.to_envelope(trace_id=trace_id)
        return JSONResponse(status_code=400, content=env.__dict__)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", None)
        env = Datam8Error(code="unexpected", message="Unexpected error.", details=None, hint=None, exit_code=10).to_envelope(
            trace_id=trace_id
        )
        return JSONResponse(status_code=500, content=env.__dict__)

    app.include_router(system_router)
    app.include_router(jobs_router)
    app.include_router(legacy_api_router)
    return app
