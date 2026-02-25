from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import uuid
import mimetypes

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..config import get_settings
from ..constants import (
    JOB_STATUS_CREATED,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP1_READY,
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
from ..repository import get_job_files, list_step1_lines
from ..schemas import (
    CouponRedeemRequest,
    Step1ConfirmRequest,
    Step2ConfirmRequest,
)
from ..services.jobs import create_new_job, load_job_or_404, require_status, save_uploaded_video
from ..services.auth import CurrentUser, require_current_user
from ..services.billing import (
    check_coupon_for_signup,
    get_user_profile,
    has_available_credits,
    redeem_coupon_for_user,
)
from ..services.cleanup import mark_job_cleanup_from_now
from ..services.step1 import confirm_step1
from ..services.step2 import confirm_step2, get_step2
from ..services.tasks import queue_job_task
from ..services.render_web import build_web_render_config, resolve_render_source_path

router = APIRouter()


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"request_id": _request_id(), "data": data}


@router.post("/jobs")
def create_job_endpoint(current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = create_new_job(current_user.user_id)
    return _ok({"job": job})


@router.get("/me")
def get_me_endpoint(current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    profile = get_user_profile(current_user.user_id, current_user.email)
    return _ok({"user": profile})


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


@router.get("/jobs/{job_id}")
def get_job_endpoint(
    job_id: str, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    return _ok({"job": job})


@router.post("/jobs/{job_id}/upload")
async def upload_job_video(
    job_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_CREATED})
    upload = await save_uploaded_video(job_id, file)
    job = load_job_or_404(job_id, current_user.user_id)
    return _ok({"job": job, "upload": upload})


@router.post("/jobs/{job_id}/step1/run")
def step1_run(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_UPLOAD_READY})
    if not has_available_credits(current_user.user_id, required=1):
        raise invalid_step_state("额度不足，请先兑换邀请码后重试")
    try:
        task_id = queue_job_task(job_id, TASK_TYPE_STEP1)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    latest = load_job_or_404(job_id, current_user.user_id)
    return _ok({"accepted": True, "task_id": task_id, "job": latest})


@router.get("/jobs/{job_id}/step1")
def step1_get(job_id: str, current_user: CurrentUser = Depends(require_current_user)) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, STEP1_GET_ALLOWED_STATUSES)
    lines = list_step1_lines(job_id)
    return _ok({"lines": lines})


@router.put("/jobs/{job_id}/step1/confirm")
def step1_confirm(
    job_id: str, request: Step1ConfirmRequest, current_user: CurrentUser = Depends(require_current_user)
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_STEP1_READY})
    lines = [item.model_dump() for item in request.lines]
    if not lines:
        raise invalid_step_state("lines cannot be empty")
    confirm_step1(job_id, lines)
    job = load_job_or_404(job_id, current_user.user_id)
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
    request: Request,
    current_user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, RENDER_GET_ALLOWED_STATUSES)
    source_url = str(request.url_for("render_source", job_id=job_id))
    try:
        render = build_web_render_config(job_id, source_url=source_url)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc
    return _ok({"render": render})


@router.get("/jobs/{job_id}/render/source", name="render_source")
def render_source(job_id: str, current_user: CurrentUser = Depends(require_current_user)):
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, RENDER_GET_ALLOWED_STATUSES)
    try:
        path = resolve_render_source_path(job_id)
    except RuntimeError as exc:
        raise invalid_step_state(str(exc)) from exc

    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path=str(path),
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )


@router.get("/jobs/{job_id}/download")
def render_download(
    job_id: str,
    cleanup: Optional[bool] = None,
    current_user: CurrentUser = Depends(require_current_user),
):
    job = load_job_or_404(job_id, current_user.user_id)
    require_status(job, {JOB_STATUS_SUCCEEDED})
    files = get_job_files(job_id)
    if not files or not files.get("final_video_path"):
        raise invalid_step_state("final video not found")
    path = Path(files["final_video_path"])
    if not path.exists():
        raise invalid_step_state("final video not found")

    settings = get_settings()
    should_cleanup = settings.cleanup_on_download if cleanup is None else bool(cleanup)
    background = (
        BackgroundTask(mark_job_cleanup_from_now, job_id, reason="downloaded")
        if should_cleanup
        else None
    )
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=path.name,
        background=background,
    )
