from __future__ import annotations

from collections import deque
import logging
import re
import threading
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import _resolve_client_ip, router
from .config import ensure_work_dirs, get_settings
from .db import init_db
from .errors import ApiError
from .services.cleanup import cleanup_on_startup
from .services.test_runner import recover_interrupted_test_runs
from .utils.common import new_request_id



_JSON_BODY_METHODS = {"POST", "PUT", "PATCH"}
_POLLING_PATH_PATTERNS = (
    re.compile(r"^/api/v1/jobs/[^/]+$"),
    re.compile(r"^/api/v1/jobs/[^/]+/test$"),
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


class _SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events_by_key: dict[str, deque[float]] = {}

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return True

        now = time.monotonic()
        cutoff = now - max(1.0, float(window_seconds))
        with self._lock:
            bucket = self._events_by_key.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _public_rate_limit_for_request(method: str, path: str) -> str | None:
    normalized_path = _normalize_path(path)
    normalized_method = method.upper()
    if normalized_method != "POST":
        return None
    if normalized_path == "/api/v1/public/invites/claim":
        return "invite_claim"
    if normalized_path == "/api/v1/public/coupons/verify":
        return "coupon_verify"
    return None


def _rate_limited_response() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "request_id": new_request_id(),
            "error": {"code": "RATE_LIMITED", "message": "请求过于频繁，请稍后再试"},
        },
    )


def _payload_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "request_id": new_request_id(),
            "error": {"code": "PAYLOAD_TOO_LARGE", "message": "请求内容过大，请精简后重试"},
        },
    )


class _RequestGuardMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        rate_limiter: _SlidingWindowRateLimiter,
        settings: Any,
    ) -> None:
        self.app = app
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        limit_key = _public_rate_limit_for_request(request.method, request.url.path)
        if limit_key is not None:
            limit = (
                self._settings.public_invite_rate_limit
                if limit_key == "invite_claim"
                else self._settings.public_coupon_verify_rate_limit
            )
            client_host = ""
            client = scope.get("client")
            if isinstance(client, tuple) and client:
                client_host = str(client[0] or "")
            client_ip = _resolve_client_ip(request) or client_host or "unknown"
            limiter_key = f"{limit_key}:{client_ip}"
            if not self._rate_limiter.allow(
                limiter_key,
                limit=limit,
                window_seconds=self._settings.public_rate_limit_window_seconds,
            ):
                response = _rate_limited_response()
                await response(scope, receive, send)
                return

        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if request.method.upper() not in _JSON_BODY_METHODS or content_type != "application/json":
            await self.app(scope, receive, send)
            return

        max_bytes = int(self._settings.max_json_body_bytes)
        content_length = str(request.headers.get("content-length") or "").strip()
        if content_length.isdigit() and int(content_length) > max_bytes:
            response = _payload_too_large_response()
            await response(scope, receive, send)
            return

        body_parts: list[bytes] = []
        total_bytes = 0
        disconnected = False
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "http.disconnect":
                disconnected = True
                break
            if message_type != "http.request":
                continue
            chunk = message.get("body", b"")
            if not isinstance(chunk, (bytes, bytearray)):
                chunk = b""
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                response = _payload_too_large_response()
                await response(scope, receive, send)
                return
            if chunk:
                body_parts.append(bytes(chunk))
            if not message.get("more_body", False):
                break

        body = b"".join(body_parts)
        body_sent = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            if disconnected:
                return {"type": "http.disconnect"}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


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
    rate_limiter = _SlidingWindowRateLimiter()
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
    app.add_middleware(
        _RequestGuardMiddleware,
        rate_limiter=rate_limiter,
        settings=settings,
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
                "request_id": new_request_id(),
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
                "request_id": new_request_id(),
                "error": {"code": "BAD_REQUEST", "message": message},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logging.exception("[web_api] unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "request_id": new_request_id(),
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
        recover_interrupted_test_runs()
        try:
            cleanup_on_startup()
        except Exception:
            logging.exception("[web_api] startup cleanup failed")

    return app


app = create_app()
