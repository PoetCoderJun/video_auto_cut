from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import ensure_work_dirs, get_settings
from .db import init_db
from .errors import ApiError
from .services.cleanup import cleanup_on_startup
from .task_queue import init_task_queue_db


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="video_auto_cut web api", version="0.1.0")
    allow_origins = list(settings.web_cors_allowed_origins)
    allow_credentials = settings.web_cors_allow_credentials
    if allow_credentials and "*" in allow_origins:
        logging.warning("[web_api] WEB_CORS_ALLOWED_ORIGINS contains '*' so credentials are disabled")
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=list(settings.web_cors_allowed_methods),
        allow_headers=list(settings.web_cors_allowed_headers),
        expose_headers=list(settings.web_cors_expose_headers),
        allow_credentials=allow_credentials,
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": _request_id(),
                "error": {"code": exc.code, "message": exc.message},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = exc.errors()
        message = details[0].get("msg", "request validation failed") if details else "request validation failed"
        return JSONResponse(
            status_code=400,
            content={
                "request_id": _request_id(),
                "error": {"code": "BAD_REQUEST", "message": message},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logging.exception("[web_api] unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "request_id": _request_id(),
                "error": {"code": "INTERNAL_ERROR", "message": "服务内部错误，请稍后重试"},
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router, prefix="/api/v1")

    @app.on_event("startup")
    def startup_event() -> None:
        ensure_work_dirs()
        init_db()
        init_task_queue_db()
        try:
            cleanup_on_startup()
        except Exception:
            logging.exception("[web_api] startup cleanup failed")

    return app


app = create_app()
