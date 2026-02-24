from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import AbstractSet

from fastapi import UploadFile

from ..config import ensure_job_dirs, get_settings
from ..constants import JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY, PROGRESS_UPLOAD_READY
from ..errors import invalid_step_state, not_found, upload_too_large
from ..repository import create_job, get_job, upsert_job_files, update_job
from ..utils.media import probe_video_stream, validate_video_extension


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


async def save_uploaded_video(job_id: str, file: UploadFile) -> dict:
    settings = get_settings()
    dirs = ensure_job_dirs(job_id)

    filename = Path(file.filename or "upload.mp4").name
    target = dirs["input"] / filename
    logging.info("[web_api] upload start job=%s filename=%s target=%s", job_id, filename, target)
    validate_video_extension(target)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0

    with target.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                output.close()
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                logging.warning(
                    "[web_api] upload too large job=%s filename=%s bytes=%s limit_mb=%s",
                    job_id,
                    filename,
                    total,
                    settings.max_upload_mb,
                )
                raise upload_too_large(f"文件超过 {settings.max_upload_mb}MB，请压缩后重试")
            output.write(chunk)

    if total <= 0:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        logging.warning("[web_api] upload empty file job=%s filename=%s", job_id, filename)
        raise invalid_step_state("上传文件为空")

    media_info = probe_video_stream(target)
    upsert_job_files(job_id, video_path=str(target))
    update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    logging.info(
        "[web_api] upload ready job=%s filename=%s bytes=%s duration=%s codec=%s",
        job_id,
        filename,
        total,
        media_info.get("duration_sec"),
        media_info.get("video_codec"),
    )
    return {
        "filename": filename,
        "size_bytes": total,
        "duration_sec": media_info.get("duration_sec"),
        "video_codec": media_info.get("video_codec"),
        "audio_codec": None,
    }
