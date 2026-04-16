from __future__ import annotations

import logging
import uuid
from typing import AbstractSet
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..constants import (
    JOB_STATUS_CREATED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_SUCCEEDED,
    PROGRESS_TEST_RUNNING,
    RENDER_GET_ALLOWED_STATUSES,
    TEST_GET_ALLOWED_STATUSES,
)
from ..config import get_settings
from ..db_repository import (
    claim_public_coupon_code,
    consume_job_export_credit,
    ensure_user,
    get_credit_balance,
    get_recent_credit_ledger,
    get_user,
    preview_coupon_code,
    redeem_coupon_code,
)
from ..errors import (
    bad_request,
    coupon_code_exhausted,
    coupon_code_expired,
    coupon_code_invalid,
    forbidden,
    invalid_step_state,
    invite_claim_exhausted,
    invite_claim_failed,
    not_found,
)
from ..job_file_repository import (
    create_job,
    get_job,
    get_job_owner_user_id,
    update_job,
    upsert_job_files,
)
from ..schemas import (
    AudioOssReadyRequest,
    ClientUploadIssueReportRequest,
    CouponRedeemRequest,
    TestConfirmRequest,
)
from ..services.jobs import mark_audio_oss_ready, save_uploaded_audio
from ..services.oss_presign import get_presigned_put_url_for_job
from ..services.auth import CurrentUser, require_current_user
from ..services.test_runner import run_test_job_background
from ..services.test import confirm_test, get_test_document
from ..utils.common import new_request_id

router = APIRouter()

def has_available_credits(user_id: str) -> bool:
    return get_credit_balance(user_id) >= 1


def load_job_or_404(job_id: str, owner_user_id: str) -> dict[str, Any]:
    job = get_job(job_id, owner_user_id=owner_user_id)
    if not job:
        raise not_found("job not found")
    return job


def require_status(job: dict[str, Any], allowed: AbstractSet[str]) -> None:
    if job.get("status") not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise invalid_step_state(f"current status={job.get('status')} expected in [{allowed_text}]")


def require_active_user(user_id: str, email: str | None = None) -> None:
    ensure_user(user_id, email)
    user = get_user(user_id)
    status = str((user or {}).get("status") or "PENDING_COUPON").upper()
    if status != "ACTIVE":
        raise forbidden("账号尚未完成邀请码激活，请先激活后再继续")


def get_user_profile(user_id: str, email: str | None = None) -> dict[str, object]:
    ensure_user(user_id, email)
    user = get_user(user_id)
    if not user:
        return {
            "user_id": user_id,
            "email": None,
            "status": "PENDING_COUPON",
            "activated_at": None,
            "credits": {"balance": 0, "recent_ledger": []},
        }
    return {
        "user_id": str(user["user_id"]),
        "email": user.get("email"),
        "status": user.get("status") or "PENDING_COUPON",
        "activated_at": user.get("activated_at"),
        "credits": {
            "balance": get_credit_balance(user_id),
            "recent_ledger": get_recent_credit_ledger(user_id, limit=20),
        },
    }


def redeem_coupon_for_user(user_id: str, code: str, email: str | None = None) -> dict[str, object]:
    ensure_user(user_id, email)
    try:
        result = redeem_coupon_code(user_id, code)
    except LookupError as exc:
        flag = str(exc)
        if flag == "COUPON_CODE_EXPIRED":
            raise coupon_code_expired("兑换码已过期，请联系管理员获取新码") from exc
        if flag == "COUPON_CODE_EXHAUSTED":
            raise coupon_code_exhausted("兑换码已用完，请联系管理员获取新码") from exc
        raise coupon_code_invalid("兑换码无效，请检查后重试") from exc
    except ValueError as exc:
        raise coupon_code_invalid("兑换码不能为空") from exc
    except RuntimeError as exc:
        raise coupon_code_invalid("兑换码服务暂不可用，请稍后再试") from exc

    return {
        "already_activated": bool(result["already_activated"]),
        "coupon_redeemed": bool(result["coupon_redeemed"]),
        "granted_credits": int(result["granted_credits"]),
        "balance": int(result["balance"]),
    }


def check_coupon_for_signup(code: str) -> dict[str, object]:
    try:
        result = preview_coupon_code(code)
    except LookupError as exc:
        flag = str(exc)
        if flag == "COUPON_CODE_EXPIRED":
            raise coupon_code_expired("邀请码已过期，请联系管理员获取新码") from exc
        if flag == "COUPON_CODE_EXHAUSTED":
            raise coupon_code_exhausted("邀请码已被使用，请联系管理员获取新码") from exc
        raise coupon_code_invalid("邀请码无效，请检查后重试") from exc
    except ValueError as exc:
        raise coupon_code_invalid("邀请码不能为空") from exc
    except RuntimeError as exc:
        raise coupon_code_invalid("邀请码服务暂不可用，请稍后再试") from exc

    return {
        "valid": True,
        "code": str(result["code"]),
        "credits": int(result["credits"]),
    }


def claim_public_invite_for_ip(ip_address: str) -> dict[str, object]:
    normalized_ip = str(ip_address or "").strip()
    if not normalized_ip:
        raise bad_request("暂时无法识别你的访问来源，请稍后重试")

    settings = get_settings()
    try:
        result = claim_public_coupon_code(
            normalized_ip,
            credits=settings.public_invite_credits,
            source="PUBLIC_WEB_INVITE",
        )
    except LookupError as exc:
        if str(exc) == "PUBLIC_INVITE_EXHAUSTED":
            raise invite_claim_exhausted("邀请码领取名额已满，请稍后再来看看") from exc
        raise invite_claim_failed("邀请码发放失败，请稍后再试") from exc
    except ValueError as exc:
        raise bad_request("暂时无法识别你的访问来源，请稍后重试") from exc
    except RuntimeError as exc:
        raise invite_claim_failed("邀请码发放失败，请稍后再试") from exc

    return {
        "code": str(result["code"]),
        "credits": int(result["credits"]),
        "already_claimed": bool(result["already_claimed"]),
    }




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
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_UPLOAD_READY})
    if not has_available_credits(current_user.user_id):
        raise invalid_step_state("额度不足，请先兑换邀请码后重试")
    update_job(
        job_id,
        status=JOB_STATUS_TEST_RUNNING,
        progress=PROGRESS_TEST_RUNNING,
        stage_code="TEST_QUEUED",
        stage_message="上传完成，正在启动字幕与章节生成...",
    )
    background_tasks.add_task(run_test_job_background, job_id)
    latest = load_job_or_404(job_id, current_user.user_id)
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
    if not has_available_credits(current_user.user_id):
        raise invalid_step_state("额度不足，请先兑换邀请码后重试")
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
    require_active_user(current_user.user_id, current_user.email)
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_TEST_CONFIRMED, JOB_STATUS_SUCCEEDED})
    try:
        owner_user_id = get_job_owner_user_id(job_id)
        if not owner_user_id:
            raise invalid_step_state("job owner not found")
        billing_result = consume_job_export_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise invalid_step_state("额度不足，请先兑换邀请码后重试") from exc
        raise

    update_job(
        job_id,
        status=JOB_STATUS_SUCCEEDED,
        progress=PROGRESS_SUCCEEDED,
        stage_code="EXPORT_SUCCEEDED",
        stage_message="视频导出成功。",
    )
    latest = load_job_or_404(job_id, current_user.user_id)
    return _ok(
        {
            "job": latest,
            "billing": {
                "consumed": bool(billing_result["consumed"]),
                "balance": int(billing_result["balance"]),
            },
        }
    )
