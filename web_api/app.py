from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import ensure_work_dirs
from .db import init_db
from .errors import ApiError
from .services.cleanup import cleanup_on_startup
from .task_queue import init_task_queue_db


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def create_app() -> FastAPI:
    app = FastAPI(title="video_auto_cut web api", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
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
                "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
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
