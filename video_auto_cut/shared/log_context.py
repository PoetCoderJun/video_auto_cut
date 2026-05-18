from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)

_ALL_CONTEXT_VARS: list[contextvars.ContextVar[str | None]] = [
    _request_id,
    _user_id,
    _job_id,
    _trace_id,
]

_FIELD_NAMES: list[str] = ["request_id", "user_id", "job_id", "trace_id"]


def get_context_fields() -> dict[str, str]:
    result: dict[str, str] = {}
    for field_name, var in zip(_FIELD_NAMES, _ALL_CONTEXT_VARS):
        value = var.get()
        if value is not None:
            result[field_name] = value
    return result


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def set_user_id(value: str | None) -> None:
    _user_id.set(value)


def set_job_id(value: str | None) -> None:
    _job_id.set(value)


def set_trace_id(value: str | None) -> None:
    _trace_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def get_user_id() -> str | None:
    return _user_id.get()


def get_job_id() -> str | None:
    return _job_id.get()


def get_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def bind_context(
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    **extra: Any,
) -> Iterator[None]:
    tokens: list[contextvars.Token[str | None]] = []
    try:
        if request_id is not None:
            tokens.append(_request_id.set(request_id))
        if user_id is not None:
            tokens.append(_user_id.set(user_id))
        if job_id is not None:
            tokens.append(_job_id.set(job_id))
        if trace_id is not None:
            tokens.append(_trace_id.set(trace_id))
        for key, value in extra.items():
            var = _get_or_create_var(key)
            tokens.append(var.set(str(value) if value is not None else None))
        yield
    finally:
        for token in tokens:
            var = token.var
            var.reset(token)


_EXTRA_VARS: dict[str, contextvars.ContextVar[str | None]] = {}


def _get_or_create_var(name: str) -> contextvars.ContextVar[str | None]:
    if name not in _EXTRA_VARS:
        _EXTRA_VARS[name] = contextvars.ContextVar(name, default=None)
    return _EXTRA_VARS[name]


def get_all_context_fields() -> dict[str, str]:
    result = get_context_fields()
    for name, var in _EXTRA_VARS.items():
        value = var.get()
        if value is not None:
            result[name] = value
    return result
