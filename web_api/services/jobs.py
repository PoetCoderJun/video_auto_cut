from __future__ import annotations

import tempfile
import logging
from pathlib import Path
from typing import AbstractSet
from typing import Any

from fastapi import UploadFile

from ..config import ensure_job_dirs, get_settings
from ..constants import (
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_SUCCEEDED,
    PROGRESS_TEST_RUNNING,
    PROGRESS_UPLOAD_READY,
)
from ..errors import invalid_step_state, not_found, upload_too_large
from ..job_file_repository import get_job, get_job_files, upsert_job_files, update_job
from ..utils.media import validate_audio_extension
from .billing import consume_export_credit, ensure_credit_available
from .oss_presign import get_oss_uploader


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


def save_uploaded_audio(job_id: str, file: UploadFile) -> dict:
    settings = get_settings()
    ensure_job_dirs(job_id)

    raw_name = Path(file.filename or "audio.m4a").name
    suffix = Path(raw_name).suffix.lower() or ".m4a"
    target = Path(f"audio{suffix}")
    logging.info(
        "[web_api] audio upload start job=%s filename=%s content_type=%s",
        job_id,
        raw_name,
        getattr(file, "content_type", None),
    )
    validate_audio_extension(target)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    temp_path: Path | None = None

    with tempfile.NamedTemporaryFile(prefix=f"{job_id}_", suffix=suffix, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                logging.warning(
                    "[web_api] audio upload too large job=%s filename=%s bytes=%s limit_mb=%s",
                    job_id,
                    raw_name,
                    total,
                    settings.max_upload_mb,
                )
                raise upload_too_large(f"文件超过 {settings.max_upload_mb}MB，请压缩后重试")
            temp_file.write(chunk)

    try:
        if total <= 0:
            logging.warning("[web_api] audio upload empty file job=%s filename=%s", job_id, raw_name)
            raise invalid_step_state("上传文件为空")

        try:
            uploader = get_oss_uploader()
        except Exception as exc:
            logging.exception("[web_api] OSS uploader unavailable job=%s filename=%s", job_id, raw_name)
            raise invalid_step_state("上传服务暂时不可用，请稍后重试。") from exc

        try:
            uploaded = uploader.upload_audio(temp_path, job_id=job_id)
        except Exception as exc:
            logging.exception("[web_api] audio upload to OSS failed job=%s filename=%s", job_id, raw_name)
            raise invalid_step_state("音频上传失败，请稍后重试。") from exc

        upsert_job_files(
            job_id,
            audio_path=None,
            asr_oss_key=uploaded.object_key,
            pending_asr_oss_key=None,
        )
        update_job(
            job_id,
            status=JOB_STATUS_UPLOAD_READY,
            progress=PROGRESS_UPLOAD_READY,
            stage_code="UPLOAD_COMPLETE",
            stage_message="上传完成，正在启动语音转写...",
        )
        logging.info(
            "[web_api] audio upload ready job=%s filename=%s object_key=%s bytes=%s",
            job_id,
            raw_name,
            uploaded.object_key,
            total,
        )
        return {
            "filename": raw_name,
            "object_key": uploaded.object_key,
            "size_bytes": total,
        }
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logging.warning("[web_api] failed to remove temp upload file job=%s path=%s", job_id, temp_path)


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
