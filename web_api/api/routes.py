from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

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
from ..db_repository import get_guest_session, set_guest_session_job
from ..errors import (
    bad_request,
    coupon_code_exhausted,
    coupon_code_expired,
    coupon_code_invalid,
    forbidden,
    invalid_step_state,
    invite_claim_exhausted,
    invite_claim_failed,
    service_unavailable,
)
from ..job_file_repository import (
    create_job,
    get_job,
    get_job_files,
    upsert_job_files,
)
from ..schemas import (
    AudioOssReadyRequest,
    ClientUploadIssueReportRequest,
    CouponRedeemRequest,
    CreateJobRequest,
    TestConfirmRequest,
    GuestSessionClaimRequest,
)
from ..services.auth import CurrentUser, RequestActor, require_current_user, require_request_actor
from ..services.account import (
    AccountServiceError,
    ClientIpUnavailableError,
    CouponCodeExhaustedError,
    CouponCodeExpiredError,
    CouponCodeInvalidError,
    GuestSessionIneligibleError,
    GuestSessionUnavailableError,
    InviteClaimExhaustedError,
    InviteClaimFailedError,
    UserActivationRequiredError,
    check_coupon_for_signup,
    claim_guest_session_for_request,
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
    save_local_uploaded_audio,
    save_local_uploaded_video,
)
from ..services.oss_presign import get_presigned_put_url_for_job
from ..services.test_runner import run_test_job_background
from ..services.test import confirm_test, get_test_document
from ..services.source_transcode import transcode_source_video_to_browser_compatible_mp4
from ..utils.common import new_request_id

router = APIRouter()


def _browser_compatible_output_name(file_name: str) -> str:
    name = str(file_name or "").strip() or "source"
    if "." in name:
        stem = name.rsplit(".", 1)[0]
    else:
        stem = name
    return f"{stem}_browser_compatible.mp4"

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


def _translate_guest_session_error(exc: AccountServiceError):
    if isinstance(exc, GuestSessionIneligibleError):
        return forbidden("当前设备已使用过免登录免费剪辑，请登录并兑换邀请码后继续")
    if isinstance(exc, GuestSessionUnavailableError):
        return service_unavailable("暂时无法开启免登录体验，请稍后重试")
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


def _ensure_actor_can_use_job_routes(actor: RequestActor) -> None:
    if actor.kind != "user":
        return
    try:
        ensure_active_user(actor.actor_id, actor.email)
    except AccountServiceError as exc:
        raise _translate_account_error(exc) from exc


def _coerce_actor(value: RequestActor | CurrentUser) -> RequestActor:
    if isinstance(value, RequestActor):
        return value
    return RequestActor(
        actor_id=value.user_id,
        kind="user",
        email=value.email,
        account=value.account,
        guest_id=None,
    )


@router.post("/jobs")
def create_job_endpoint(
    request: CreateJobRequest = Body(default_factory=CreateJobRequest),
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    if actor.kind == "guest" and actor.guest_id:
        guest_session = get_guest_session(actor.guest_id)
        remaining = int((guest_session or {}).get("free_uses_remaining") or 0)
        status = str((guest_session or {}).get("status") or "ACTIVE").upper()
        if remaining < 1 or status != "ACTIVE":
            raise invalid_step_state("当前设备已使用过免登录免费剪辑，请登录并兑换邀请码后继续")
        existing_job_id = str((guest_session or {}).get("job_id") or "").strip()
        if existing_job_id:
            existing_job = get_job(existing_job_id, owner_user_id=actor.actor_id)
            if existing_job and existing_job.get("status") != "FAILED":
                return _ok({"job": existing_job})

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = create_job(job_id, JOB_STATUS_CREATED, actor.actor_id, script=request.script)
    if actor.kind == "guest" and actor.guest_id:
        set_guest_session_job(actor.guest_id, job_id)
    logging.info(
        "[web_api] route=create_job actor=%s kind=%s job=%s script_present=%s",
        actor.actor_id,
        actor.kind,
        job.get("job_id"),
        bool(request.script.strip()),
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
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    logging.warning(
        "[web_api] client upload issue actor=%s kind=%s stage=%s page=%s file=%s size=%s type=%s error_name=%s error=%s friendly=%s client=%s ua=%s",
        actor.actor_id,
        actor.kind,
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


@router.post("/public/guest/session")
def claim_guest_session_endpoint(
    payload: GuestSessionClaimRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        result = claim_guest_session_for_request(
            ip_address=_resolve_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            device_fingerprint=payload.device_fingerprint,
        )
    except AccountServiceError as exc:
        raise _translate_guest_session_error(exc) from exc
    return _ok({"guest": result})


@router.post("/source/browser-compatible")
def source_browser_compatible(
    background_tasks: BackgroundTasks,
    source_file: UploadFile = File(...),
    actor: RequestActor = Depends(require_request_actor),
):
    _ensure_actor_can_use_job_routes(actor)

    temp_dir = Path(tempfile.mkdtemp(prefix="video_auto_cut_source_transcode_"))
    input_path = temp_dir / (source_file.filename or "source.bin")
    output_path = temp_dir / _browser_compatible_output_name(source_file.filename or "source")
    try:
        with input_path.open("wb") as fh:
            shutil.copyfileobj(source_file.file, fh)
        transcode_source_video_to_browser_compatible_mp4(
            input_path=input_path,
            output_path=output_path,
        )
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise invalid_step_state(str(exc)) from exc
    finally:
        source_file.file.close()

    background_tasks.add_task(shutil.rmtree, temp_dir, True)
    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename=output_path.name,
    )


@router.get("/jobs/{job_id}")
def get_job_endpoint(
    job_id: str, actor: RequestActor = Depends(require_request_actor)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, actor.actor_id)
    return _ok({"job": job})


@router.post("/jobs/{job_id}/oss-upload-url")
def get_oss_upload_url(
    job_id: str,
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    _ensure_actor_can_use_job_routes(actor)
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    settings = get_settings()

    oss_ready = bool(
        settings.asr_oss_endpoint
        and settings.asr_oss_bucket
        and settings.asr_oss_access_key_id
        and settings.asr_oss_access_key_secret
    )
    if not oss_ready:
        raise service_unavailable("上传服务暂未配置，请稍后再试。")
    put_url, object_key = get_presigned_put_url_for_job(
        job_id,
        suffix=".mp3",
        content_type="audio/mpeg",
    )
    upsert_job_files(job_id, pending_asr_oss_key=object_key)
    return _ok({"put_url": put_url, "object_key": object_key})


@router.post("/jobs/{job_id}/audio-oss-ready")
def audio_oss_ready(
    job_id: str,
    request: AudioOssReadyRequest,
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    _ensure_actor_can_use_job_routes(actor)
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})
    result = mark_audio_oss_ready(job_id, request.object_key)
    job = load_job_or_404(job_id, actor.actor_id)
    logging.info(
        "[web_api] route=audio_oss_ready actor=%s kind=%s job=%s object_key=%s",
        actor.actor_id,
        actor.kind,
        job_id,
        request.object_key,
    )
    return _ok({"job": job, "upload": result})


@router.post("/jobs/{job_id}/audio-upload-local")
def audio_upload_local(
    job_id: str,
    audio_file: UploadFile = File(...),
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    _ensure_actor_can_use_job_routes(actor)
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})

    try:
        result = save_local_uploaded_audio(job_id, audio_file)
    finally:
        audio_file.file.close()

    job = load_job_or_404(job_id, actor.actor_id)
    logging.info(
        "[web_api] route=audio_upload_local actor=%s kind=%s job=%s audio_path=%s",
        actor.actor_id,
        actor.kind,
        job_id,
        result.get("audio_path"),
    )
    return _ok({"job": job, "upload": result})


@router.post("/jobs/{job_id}/source-upload-local")
def source_upload_local(
    job_id: str,
    source_file: UploadFile = File(...),
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    _ensure_actor_can_use_job_routes(actor)
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY})

    try:
        result = save_local_uploaded_video(job_id, source_file)
    finally:
        source_file.file.close()

    job = load_job_or_404(job_id, actor.actor_id)
    logging.info(
        "[web_api] route=source_upload_local actor=%s kind=%s job=%s video_path=%s",
        actor.actor_id,
        actor.kind,
        job_id,
        result.get("video_path"),
    )
    return _ok({"job": job, "upload": result})


@router.post("/jobs/{job_id}/test/run")
def test_run(
    job_id: str,
    background_tasks: BackgroundTasks,
    actor: RequestActor = Depends(require_request_actor),
) -> dict[str, Any]:
    _ensure_actor_can_use_job_routes(actor)
    try:
        latest = queue_test_run(job_id, actor.actor_id)
    except BillingServiceError as exc:
        raise _translate_billing_error(exc) from exc
    background_tasks.add_task(run_test_job_background, job_id)
    logging.info(
        "[web_api] route=test_run actor=%s kind=%s job=%s mode=background-task",
        actor.actor_id,
        actor.kind,
        job_id,
    )
    return _ok({"accepted": True, "job": latest})


@router.get("/jobs/{job_id}/test")
def test_get(job_id: str, actor: RequestActor = Depends(require_request_actor)) -> dict[str, Any]:
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, TEST_GET_ALLOWED_STATUSES)
    document = get_test_document(job_id)
    logging.debug(
        "[web_api] route=test_get actor=%s kind=%s job=%s line_count=%s chapter_count=%s",
        actor.actor_id,
        actor.kind,
        job_id,
        len(document["lines"]),
        len(document["chapters"]),
    )
    return _ok(document)


@router.put("/jobs/{job_id}/test/confirm")
def test_confirm(
    job_id: str, request: TestConfirmRequest, actor: RequestActor = Depends(require_request_actor)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, actor.actor_id)
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
    job = load_job_or_404(job_id, actor.actor_id)
    logging.info(
        "[web_api] route=test_confirm actor=%s kind=%s job=%s line_count=%s chapter_count=%s",
        actor.actor_id,
        actor.kind,
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
    current_user: RequestActor | CurrentUser = Depends(require_request_actor),
) -> dict[str, Any]:
    actor = _coerce_actor(current_user)
    job = load_job_or_404(job_id, actor.actor_id)
    require_status(job, RENDER_GET_ALLOWED_STATUSES)
    try:
        ensure_credit_available(actor.actor_id)
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
    current_user: RequestActor | CurrentUser = Depends(require_request_actor),
) -> dict[str, Any]:
    actor = _coerce_actor(current_user)
    _ensure_actor_can_use_job_routes(actor)
    try:
        latest, billing_result = complete_render_export(job_id, actor.actor_id)
    except BillingServiceError as exc:
        raise _translate_billing_error(exc) from exc
    return _ok(
        {
            "job": latest,
            "billing": billing_result,
        }
    )
