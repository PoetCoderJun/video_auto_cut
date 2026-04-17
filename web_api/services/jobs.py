from __future__ import annotations

import logging
from typing import AbstractSet
from typing import Any

from ..constants import (
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_SUCCEEDED,
    PROGRESS_TEST_RUNNING,
    PROGRESS_UPLOAD_READY,
)
from ..errors import invalid_step_state, not_found
from ..job_file_repository import get_job, get_job_files, upsert_job_files, update_job
from .billing import consume_export_credit, ensure_credit_available


def load_job_or_404(job_id: str, owner_user_id: str) -> dict[str, Any]:
    job = get_job(job_id, owner_user_id=owner_user_id)
    if not job:
        raise not_found("job not found")
    return job


def require_status(job: dict[str, Any], allowed: AbstractSet[str]) -> None:
    if job.get("status") not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise invalid_step_state(f"current status={job.get('status')} expected in [{allowed_text}]")


def queue_test_run(job_id: str, user_id: str) -> dict[str, Any]:
    job = load_job_or_404(job_id, user_id)
    require_status(job, {JOB_STATUS_UPLOAD_READY})
    ensure_credit_available(user_id)
    update_job(
        job_id,
        status=JOB_STATUS_TEST_RUNNING,
        progress=PROGRESS_TEST_RUNNING,
        stage_code="TEST_QUEUED",
        stage_message="上传完成，正在启动字幕与章节生成...",
    )
    return load_job_or_404(job_id, user_id)


def complete_render_export(job_id: str, user_id: str) -> tuple[dict[str, Any], dict[str, object]]:
    job = load_job_or_404(job_id, user_id)
    require_status(job, {JOB_STATUS_TEST_CONFIRMED, JOB_STATUS_SUCCEEDED})
    billing = consume_export_credit(job_id)
    update_job(
        job_id,
        status=JOB_STATUS_SUCCEEDED,
        progress=PROGRESS_SUCCEEDED,
        stage_code="EXPORT_SUCCEEDED",
        stage_message="视频导出成功。",
    )
    latest = load_job_or_404(job_id, user_id)
    return latest, billing


def mark_audio_oss_ready(job_id: str, object_key: str) -> dict:
    """Mark job as ready after client uploaded audio directly to OSS."""
    files = get_job_files(job_id) or {}
    expected_object_key = str(files.get("pending_asr_oss_key") or "").strip()
    normalized_object_key = str(object_key or "").strip()
    if not expected_object_key:
        raise invalid_step_state("请重新获取上传地址后，再确认上传完成")
    if normalized_object_key != expected_object_key:
        raise invalid_step_state("上传对象校验失败，请重新上传后重试")

    upsert_job_files(
        job_id,
        audio_path=None,
        asr_oss_key=normalized_object_key,
        pending_asr_oss_key=None,
    )
    update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    logging.info(
        "[web_api] audio OSS upload ready job=%s object_key=%s",
        job_id,
        normalized_object_key,
    )
    return {"object_key": normalized_object_key}
