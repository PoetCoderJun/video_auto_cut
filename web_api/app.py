from __future__ import annotations

import logging
import re
import time
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


_POLLING_PATH_PATTERNS = (
    re.compile(r"^/api/v1/jobs/[^/]+$"),
    re.compile(r"^/api/v1/jobs/[^/]+/step1$"),
)


def _is_polling_path(path: str) -> bool:
    normalized_path = path.rstrip("/") or "/"
    return any(pattern.fullmatch(normalized_path) for pattern in _POLLING_PATH_PATTERNS)


def _should_suppress_request_log(method: str, path: str) -> bool:
    normalized_method = method.upper()
    if normalized_method == "OPTIONS":
        return True
    return normalized_method == "GET" and _is_polling_path(path)


class _SuppressPollingAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = getattr(record, "args", ())
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        method = str(args[1])
        path = str(args[2]).split("?", 1)[0]
        return not _should_suppress_request_log(method, path)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root_logger.setLevel(logging.INFO)
    logging.getLogger("web_api").setLevel(logging.INFO)
    logging.getLogger("video_auto_cut").setLevel(logging.INFO)
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(log_filter, _SuppressPollingAccessFilter) for log_filter in access_logger.filters):
        access_logger.addFilter(_SuppressPollingAccessFilter())


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    app = FastAPI(title="video_auto_cut web api", version="0.1.0")
    allow_origins = list(settings.web_cors_allowed_origins)
    allow_credentials = settings.web_cors_allow_credentials
    logging.info("[web_api] CORS allow_origins=%s allow_credentials=%s", allow_origins, allow_credentials)
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

    @app.middleware("http")
    async def log_http_requests(request: Request, call_next):
        started_at = time.perf_counter()
        suppress_request_log = _should_suppress_request_log(request.method, request.url.path)
        client_host = getattr(request.client, "host", "") if request.client else ""
        if not suppress_request_log:
            logging.info(
                "[web_api] request start method=%s path=%s query=%s client=%s",
                request.method,
                request.url.path,
                request.url.query,
                client_host,
            )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logging.exception(
                "[web_api] request failed method=%s path=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if not suppress_request_log:
            logging.info(
                "[web_api] request done method=%s path=%s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response

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
