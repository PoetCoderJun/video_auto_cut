from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    code: str
    message: str
    status_code: int


def bad_request(message: str) -> ApiError:
    return ApiError(code="BAD_REQUEST", message=message, status_code=400)


def not_found(message: str) -> ApiError:
    return ApiError(code="NOT_FOUND", message=message, status_code=404)


def upload_too_large(message: str) -> ApiError:
    return ApiError(code="UPLOAD_TOO_LARGE", message=message, status_code=413)


def unsupported_video_format(message: str) -> ApiError:
    return ApiError(code="UNSUPPORTED_VIDEO_FORMAT", message=message, status_code=422)


def invalid_step_state(message: str) -> ApiError:
    return ApiError(code="INVALID_STEP_STATE", message=message, status_code=409)


def unauthorized(message: str) -> ApiError:
    return ApiError(code="UNAUTHORIZED", message=message, status_code=401)


def forbidden(message: str) -> ApiError:
    return ApiError(code="FORBIDDEN", message=message, status_code=403)


def coupon_code_invalid(message: str) -> ApiError:
    return ApiError(code="COUPON_CODE_INVALID", message=message, status_code=422)


def coupon_code_expired(message: str) -> ApiError:
    return ApiError(code="COUPON_CODE_EXPIRED", message=message, status_code=422)


def coupon_code_exhausted(message: str) -> ApiError:
    return ApiError(code="COUPON_CODE_EXHAUSTED", message=message, status_code=422)
