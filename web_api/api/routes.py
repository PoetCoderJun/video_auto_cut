from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..constants import (
    JOB_STATUS_CREATED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_UPLOAD_READY,
    RENDER_GET_ALLOWED_STATUSES,
    TEST_GET_ALLOWED_STATUSES,
)
from ..config import get_settings
from ..errors import (
    bad_request,
    coupon_code_exhausted,
    coupon_code_expired,
    coupon_code_invalid,
    forbidden,
    invalid_step_state,
    invite_claim_exhausted,
    invite_claim_failed,
)
from ..job_file_repository import (
    create_job,
    upsert_job_files,
)
from ..schemas import (
    AudioOssReadyRequest,
    ClientUploadIssueReportRequest,
    CouponRedeemRequest,
    TestConfirmRequest,
)
from ..services.auth import CurrentUser, require_current_user
from ..services.account import (
    AccountServiceError,
    ClientIpUnavailableError,
    CouponCodeExhaustedError,
    CouponCodeExpiredError,
    CouponCodeInvalidError,
    InviteClaimExhaustedError,
    InviteClaimFailedError,
    UserActivationRequiredError,
    check_coupon_for_signup,
    claim_public_invite_for_ip,
    ensure_active_user,
    get_user_profile,
    redeem_coupon_for_user,
)
from ..services.billing import BillingServiceError, InsufficientCreditsError, ensure_credit_available
from ..services.jobs import (
    complete_render_export,
    load_job_or_404,
    mark_audio_oss_ready,
    queue_test_run,
    require_status,
    save_uploaded_audio,
)
from ..services.oss_presign import get_presigned_put_url_for_job
from ..services.test_runner import run_test_job_background
from ..services.test import confirm_test, get_test_document
from ..utils.common import new_request_id

router = APIRouter()

def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"request_id": new_request_id(), "data": data}


def _build_render_config(*args: Any, **kwargs: Any) -> Any:
    from ..services.render_web import build_web_render_config

    return build_web_render_config(*args, **kwargs)


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


def _translate_account_error(exc: AccountServiceError):
    if isinstance(exc, UserActivationRequiredError):
        return forbidden("账号尚未完成邀请码激活，请先激活后再继续")
    if isinstance(exc, CouponCodeExpiredError):
        return coupon_code_expired("兑换码已过期，请联系管理员获取新码")
    if isinstance(exc, CouponCodeExhaustedError):
        return coupon_code_exhausted("兑换码已用完，请联系管理员获取新码")
    if isinstance(exc, CouponCodeInvalidError):
        return coupon_code_invalid("兑换码无效，请检查后重试")
    if isinstance(exc, InviteClaimExhaustedError):
        return invite_claim_exhausted("邀请码领取名额已满，请稍后再来看看")
    if isinstance(exc, InviteClaimFailedError):
        return invite_claim_failed("邀请码发放失败，请稍后再试")
    if isinstance(exc, ClientIpUnavailableError):
        return bad_request("暂时无法识别你的访问来源，请稍后重试")
    raise exc


def _translate_signup_coupon_error(exc: AccountServiceError):
    if isinstance(exc, CouponCodeExpiredError):
        return coupon_code_expired("邀请码已过期，请联系管理员获取新码")
    if isinstance(exc, CouponCodeExhaustedError):
        return coupon_code_exhausted("邀请码已被使用，请联系管理员获取新码")
    if isinstance(exc, CouponCodeInvalidError):
        return coupon_code_invalid("邀请码无效，请检查后重试")
    raise exc


def _translate_billing_error(exc: BillingServiceError):
    if isinstance(exc, InsufficientCreditsError):
        return invalid_step_state("额度不足，请先兑换邀请码后重试")
    raise exc


@router.post("/jobs")
def create_job_endpoint(current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = create_job(job_id, JOB_STATUS_CREATED, current_user.user_id)
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
    try:
        result = redeem_coupon_for_user(current_user.user_id, request.code, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
    profile = get_user_profile(current_user.user_id, current_user.email)
    return _ok({"coupon": result, "user": profile})


@router.post("/public/coupons/verify")
def verify_coupon_endpoint(request: CouponRedeemRequest) -> dict[str, Any]:
    try:
        result = check_coupon_for_signup(request.code)
    except AccountServiceError as exc:
        raise _translate_signup_coupon_error(exc) from exc
    return _ok({"coupon": result})


@router.post("/public/invites/claim")
def claim_public_invite_endpoint(request: Request) -> dict[str, Any]:
    try:
        result = claim_public_invite_for_ip(_resolve_client_ip(request))
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
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
    try:
        ensure_active_user(current_user.user_id, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    suffix = ".mp3" if (format or "").strip().lower() == "mp3" else ".wav"
    settings = get_settings()

    oss_ready = bool(
        settings.asr_oss_endpoint
        and settings.asr_oss_bucket
        and settings.asr_oss_access_key_id
        and settings.asr_oss_access_key_secret
    )
    if not oss_ready:
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
    try:
        ensure_active_user(current_user.user_id, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
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
    try:
        ensure_active_user(current_user.user_id, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    upload = await run_in_threadpool(save_uploaded_audio, job_id, file)
    job = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=upload_audio user=%s job=%s filename=%s bytes=%s",
        current_user.user_id,
        job_id,
        upload.get("filename"),
        upload.get("size_bytes"),
    )
    return _ok({"job": job, "upload": upload})


@router.post("/jobs/{job_id}/test/run")
def test_run(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    try:
        ensure_active_user(current_user.user_id, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
    try:
        latest = queue_test_run(job_id, current_user.user_id)
    except BillingServiceError as exc:
        raise _translate_billing_error(exc) from exc
    background_tasks.add_task(run_test_job_background, job_id)
    logging.info(
        "[web_api] route=test_run user=%s job=%s mode=background-task",
        current_user.user_id,
        job_id,
    )
    return _ok({"accepted": True, "job": latest})


@router.get("/jobs/{job_id}/test")
def test_get(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, TEST_GET_ALLOWED_STATUSES)
    document = get_test_document(job_id)
    logging.debug(
        "[web_api] route=test_get user=%s job=%s line_count=%s chapter_count=%s",
        current_user.user_id,
        job_id,
        len(document["lines"]),
        len(document["chapters"]),
    )
    return _ok(document)


@router.put("/jobs/{job_id}/test/confirm")
def test_confirm(
    job_id: str, request: TestConfirmRequest, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_TEST_READY})
    lines = [item.model_dump() for item in request.lines]
    chapters = [item.model_dump() for item in request.chapters]
    if not lines:
        raise invalid_step_state("lines cannot be empty")
    if not chapters:
        raise invalid_step_state("chapters cannot be empty")
    try:
        confirmed = confirm_test(
            job_id,
            lines,
            chapters,
            expected_revision=request.expected_revision,
        )
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    job = load_job_or_404(job_id, current_user.user_id)
    logging.info(
        "[web_api] route=test_confirm user=%s job=%s line_count=%s chapter_count=%s",
        current_user.user_id,
        job_id,
        len(lines),
        len(chapters),
    )
    return _ok({"confirmed": True, "status": job["status"], "document_revision": confirmed["document_revision"]})


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
    try:
        ensure_credit_available(current_user.user_id)
    except BillingServiceError as exc:
        raise _translate_billing_error(exc) from exc
    try:
        render = _build_render_config(
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
    try:
        ensure_active_user(current_user.user_id, current_user.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc
    try:
        latest, billing_result = complete_render_export(job_id, current_user.user_id)
    except BillingServiceError as exc:
        raise _translate_billing_error(exc) from exc
    return _ok(
        {
            "job": latest,
            "billing": billing_result,
        }
    )
