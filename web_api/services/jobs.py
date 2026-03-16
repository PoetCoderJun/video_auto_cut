from __future__ import annotations

import tempfile
import logging
import uuid
from pathlib import Path
from typing import AbstractSet

from fastapi import UploadFile

from ..config import ensure_job_dirs, get_settings
from ..constants import JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY, PROGRESS_UPLOAD_READY
from ..errors import invalid_step_state, not_found, upload_too_large
from ..repository import create_job, get_job, upsert_job_files, update_job
from ..utils.media import validate_audio_extension
from .oss_presign import get_oss_uploader


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def create_new_job(owner_user_id: str) -> dict:
    job_id = new_job_id()
    ensure_job_dirs(job_id)
    return create_job(job_id, JOB_STATUS_CREATED, owner_user_id)


def load_job_or_404(job_id: str, owner_user_id: str) -> dict:
    job = get_job(job_id, owner_user_id=owner_user_id)
    if not job:
        raise not_found("job not found")
    return job


def require_status(job: dict, allowed: AbstractSet[str]) -> None:
    if job.get("status") not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise invalid_step_state(f"current status={job.get('status')} expected in [{allowed_text}]")


async def save_uploaded_audio(job_id: str, file: UploadFile) -> dict:
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
            chunk = await file.read(1024 * 1024)
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

        upsert_job_files(job_id, audio_path=None, asr_oss_key=uploaded.object_key)
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
    upsert_job_files(job_id, asr_oss_key=object_key)
    update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    logging.info("[web_api] audio OSS upload ready job=%s object_key=%s", job_id, object_key)
    return {"object_key": object_key}
