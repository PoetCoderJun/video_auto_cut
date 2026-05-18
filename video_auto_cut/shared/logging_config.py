from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from .log_context import get_all_context_fields


_LOG_LEVEL_NAMES: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        fields = get_all_context_fields()
        for key, value in fields.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "pathname") and record.pathname:
            log_entry["source"] = f"{record.pathname}:{record.lineno}"

        if record.exc_info:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)

        context_fields = get_all_context_fields()
        for key, value in context_fields.items():
            log_entry[key] = value

        extra_keys = set(vars(record).keys()) - {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "process",
            "processName",
            "message",
            "exc_info",
            "exc_text",
            "stack_info",
            "request_id",
            "user_id",
            "job_id",
            "trace_id",
        }
        for key in extra_keys:
            if not key.startswith("_"):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(fmt=None, datefmt=None)

    def format(self, record: logging.LogRecord) -> str:
        parts: list[str] = [
            self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            record.levelname,
            record.name,
        ]

        context = get_all_context_fields()
        if context:
            ctx_parts = [f"{k}={v}" for k, v in context.items()]
            parts.append(f"[{', '.join(ctx_parts)}]")

        parts.append(record.getMessage())

        if record.exc_info:
            parts.append("\n")
            parts.append(self.formatException(record.exc_info))

        return " ".join(parts)


def _is_tty() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def configure_logging(
    *,
    level: int | str | None = None,
    format_type: str | None = None,
    logger_names: list[str] | None = None,
) -> None:
    if level is None:
        level = _LOG_LEVEL_NAMES.get((os.getenv("LOG_LEVEL", "INFO")).upper().strip(), logging.INFO)
    if isinstance(level, str):
        level = _LOG_LEVEL_NAMES.get(level.upper(), logging.INFO)

    if format_type is None:
        env_format = (os.getenv("LOG_FORMAT", "")).lower().strip()
        if env_format == "json":
            format_type = "json"
        elif env_format == "text":
            format_type = "text"
        else:
            format_type = "json" if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("DOCKER_CONTAINER") else ("text" if _is_tty() else "json")

    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    if format_type == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(_TextFormatter())

    handler.addFilter(_ContextFilter())
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for name in (logger_names or []) + ["web_api", "video_auto_cut"]:
        logging.getLogger(name).setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
