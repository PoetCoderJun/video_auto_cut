from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from ..constants import (
    JOB_STATUS_CREATED,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP1_READY,
    JOB_STATUS_STEP2_CONFIRMED,
    JOB_STATUS_STEP2_READY,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_UPLOAD_READY,
    RENDER_GET_ALLOWED_STATUSES,
    STEP1_GET_ALLOWED_STATUSES,
    STEP2_GET_ALLOWED_STATUSES,
    TASK_TYPE_STEP1,
    TASK_TYPE_STEP2,
)
from ..errors import invalid_step_state
from ..repository import list_step1_lines, upsert_job_files
from ..schemas import (
    AudioOssReadyRequest,
    ClientUploadIssueReportRequest,
    CouponRedeemRequest,
    Step1ConfirmRequest,
    Step2ConfirmRequest,
)
from ..services.jobs import (
    create_new_job,
    load_job_or_404,
    require_status,
    save_uploaded_audio,
    mark_audio_oss_ready,
)
from ..config import get_settings
from ..services.oss_presign import get_presigned_put_url_for_job
from ..services.auth import CurrentUser, require_current_user
from ..services.billing import (
    claim_public_invite_for_ip,
    check_coupon_for_signup,
    get_user_profile,
    has_available_credits,
    require_active_user,
    redeem_coupon_for_user,
)
from ..services.step1 import confirm_step1
from ..services.step2 import confirm_step2, get_step2
from ..services.tasks import queue_job_task
from ..services.render_completion import mark_render_success
from ..services.render_web import build_web_render_config

router = APIRouter()


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"request_id": _request_id(), "data": data}


def _normalize_ip_candidate(value: str | None) -> str:
    candidate = str(value or "").strip().strip('"')
    if not candidate or candidate.lower() == "unknown":
        return ""
    if candidate.startswith("["):
        closing = candidate.find("]")
        if closing > 1:
            return candidate[1:closing]
    if candidate.count(":") == 1:
        host, port = candidate.rsplit(":", 1)
        if "." in host and port.isdigit():
            return host
    return candidate


def _parse_forwarded_header(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for entry in raw.split(","):
        for part in entry.split(";"):
            key, sep, token = part.strip().partition("=")
            if sep and key.strip().lower() == "for":
                candidate = _normalize_ip_candidate(token)
                if candidate:
                    return candidate
    return ""


def _resolve_client_ip(request: Request) -> str:
    for header_name in ("cf-connecting-ip", "true-client-ip"):
        candidate = _normalize_ip_candidate(request.headers.get(header_name))
        if candidate:
            return candidate

    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        candidate = _normalize_ip_candidate(forwarded.split(",")[0].strip())
        if candidate:
            return candidate

    real_ip = _normalize_ip_candidate(request.headers.get("x-real-ip"))
    if real_ip:
        return real_ip

    forwarded_header = _parse_forwarded_header(request.headers.get("forwarded"))
    if forwarded_header:
        return forwarded_header

    client = getattr(request, "client", None)
    host = _normalize_ip_candidate(getattr(client, "host", None))
    if host:
        return host

    return ""


@router.post("/jobs")
def create_job_endpoint(current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = create_new_job(current_user.user_id)
    logging.info(
        "[web_api] route=create_job user=%s job=%s",
        current_user.user_id,
        job.get("job_id"),
    )
    return _ok({"job": job})


@router.get("/me")
def get_me_endpoint(current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    profile = get_user_profile(current_user.user_id, current_user.email)
    return _ok({"user": profile})


@router.post("/client/upload-issues")
def report_client_upload_issue_endpoint(
    payload: ClientUploadIssueReportRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    logging.warning(
        "[web_api] client upload issue user=%s stage=%s page=%s file=%s size=%s type=%s error_name=%s error=%s friendly=%s client=%s ua=%s",
        current_user.user_id,
        payload.stage,
        payload.page,
        payload.file_name,
        payload.file_size_bytes,
        payload.file_type,
        payload.error_name,
        payload.error_message,
        payload.friendly_message,
        _resolve_client_ip(request),
        payload.user_agent,
    )
    return _ok({"accepted": True})


@router.post("/auth/coupon/redeem")
def redeem_coupon_endpoint(
    request: CouponRedeemRequest,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    result = redeem_coupon_for_user(current_user.user_id, request.code, current_user.email)
    profile = get_user_profile(current_user.user_id, current_user.email)
    return _ok({"coupon": result, "user": profile})


@router.post("/public/coupons/verify")
def verify_coupon_endpoint(request: CouponRedeemRequest) -> dict[str, Any]:
    result = check_coupon_for_signup(request.code)
    return _ok({"coupon": result})


@router.post("/public/invites/claim")
def claim_public_invite_endpoint(request: Request) -> dict[str, Any]:
    result = claim_public_invite_for_ip(_resolve_client_ip(request))
    return _ok({"invite": result})


@router.get("/jobs/{job_id}")
def get_job_endpoint(
    job_id: str, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    return _ok({"job": job})


@router.post("/jobs/{job_id}/oss-upload-url")
def get_oss_upload_url(
    job_id: str,
    format: str | None = Query(default="mp3", description="mp3 or wav"),
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    suffix = ".mp3" if (format or "").strip().lower() == "mp3" else ".wav"
    settings = get_settings()

    # 百炼临时 OSS 仅由后端 fallback 使用，前端不直传
    oss_ready = bool(
        settings.asr_oss_endpoint
        and settings.asr_oss_bucket
        and settings.asr_oss_access_key_id
        and settings.asr_oss_access_key_secret
    )
    if not oss_ready or settings.use_dashscope_temp_oss:
        raise HTTPException(
            status_code=503,
            detail="Direct OSS upload unavailable. Audio will be uploaded via API instead.",
        )
    put_url, object_key = get_presigned_put_url_for_job(job_id, suffix=suffix)
    upsert_job_files(job_id, pending_asr_oss_key=object_key)
    return _ok({"put_url": put_url, "object_key": object_key})


@router.post("/jobs/{job_id}/audio-oss-ready")
def audio_oss_ready(
    job_id: str,
    request: AudioOssReadyRequest,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    result = mark_audio_oss_ready(job_id, request.object_key)
    job = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=audio_oss_ready user=%s job=%s object_key=%s",
        current_user.user_id,
        job_id,
        request.object_key,
    )
    return _ok({"job": job, "upload": result})


@router.post("/jobs/{job_id}/audio")
async def upload_job_audio(
    job_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    upload = await save_uploaded_audio(job_id, file)
    job = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=upload_audio user=%s job=%s filename=%s bytes=%s",
        current_user.user_id,
        job_id,
        upload.get("filename"),
        upload.get("size_bytes"),
    )
    return _ok({"job": job, "upload": upload})


@router.post("/jobs/{job_id}/step1/run")
def step1_run(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_UPLOAD_READY})
    if not has_available_credits(current_user.user_id, required=1):
        raise invalid_step_state("额度不足，请先兑换邀请码后重试")
    try:
        task_id = queue_job_task(job_id, TASK_TYPE_STEP1)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    latest = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=step1_run user=%s job=%s task_id=%s",
        current_user.user_id,
        job_id,
        task_id,
    )
    return _ok({"accepted": True, "task_id": task_id, "job": latest})


@router.get("/jobs/{job_id}/step1")
def step1_get(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, STEP1_GET_ALLOWED_STATUSES)
    lines = list_step1_lines(job_id)
    logging.debug(
        "[web_api] route=step1_get user=%s job=%s line_count=%s",
        current_user.user_id,
        job_id,
        len(lines),
    )
    return _ok({"lines": lines})


@router.put("/jobs/{job_id}/step1/confirm")
def step1_confirm(
    job_id: str, request: Step1ConfirmRequest, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_STEP1_READY, JOB_STATUS_STEP2_READY})
    lines = [item.model_dump() for item in request.lines]
    if not lines:
        raise invalid_step_state("lines cannot be empty")
    confirm_step1(job_id, lines)
    job = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=step1_confirm user=%s job=%s line_count=%s",
        current_user.user_id,
        job_id,
        len(lines),
    )
    return _ok({"confirmed": True, "status": job["status"]})


@router.post("/jobs/{job_id}/step2/run")
def step2_run(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_STEP1_CONFIRMED})
    try:
        task_id = queue_job_task(job_id, TASK_TYPE_STEP2)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    latest = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=step2_run user=%s job=%s task_id=%s",
        current_user.user_id,
        job_id,
        task_id,
    )
    return _ok({"accepted": True, "task_id": task_id, "job": latest})


@router.get("/jobs/{job_id}/step2")
def step2_get(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, STEP2_GET_ALLOWED_STATUSES)
    chapters = get_step2(job_id)
    return _ok({"chapters": chapters})


@router.put("/jobs/{job_id}/step2/confirm")
def step2_confirm(
    job_id: str, request: Step2ConfirmRequest, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_STEP2_READY})
    chapters = [item.model_dump() for item in request.chapters]
    if not chapters:
        raise invalid_step_state("chapters cannot be empty")
    confirm_step2(job_id, chapters)
    job = load_job_or_404(job_id, current_user.user_id)
    return _ok({"confirmed": True, "status": job["status"]})


@router.get("/jobs/{job_id}/render/config")
def render_config(
    job_id: str,
    width: int | None = None,
    height: int | None = None,
    fps: float | None = None,
    duration_sec: float | None = None,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, RENDER_GET_ALLOWED_STATUSES)
    if not has_available_credits(current_user.user_id, required=1):
        raise invalid_step_state("额度不足，请先兑换邀请码后重试")
    try:
        render = build_web_render_config(
            job_id,
            width=width,
            height=height,
            fps=fps,
            duration_sec=duration_sec,
        )
    except (RuntimeError, ValueError) as exc:
        raise invalid_step_state(str(exc)) from exc
    return _ok({"render": render})


@router.post("/jobs/{job_id}/render/complete")
def render_complete(
    job_id: str,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_STEP2_CONFIRMED, JOB_STATUS_SUCCEEDED})
    try:
        billing = mark_render_success(job_id)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    latest = load_job_or_404(job_id, current_user.user_id)
    return _ok({"job": latest, "billing": billing})
