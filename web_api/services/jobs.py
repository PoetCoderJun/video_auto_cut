from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import AbstractSet
from typing import Any

from fastapi import UploadFile

from ..config import ensure_job_dirs
from ..constants import (
    ALLOWED_VIDEO_EXTENSIONS,
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
from .billing import consume_export_credit, consume_test_credit


_LOCAL_AUDIO_UPLOAD_CHUNK_SIZE = 1024 * 1024
_DEFAULT_LOCAL_AUDIO_UPLOAD_MAX_MB = 2048


def _has_uploaded_audio(files: dict[str, Any] | None) -> bool:
    payload = files or {}
    return bool(payload.get("audio_path") or payload.get("asr_oss_key"))


def _local_audio_upload_max_bytes() -> int:
    raw = (
        os.getenv("WEB_LOCAL_AUDIO_UPLOAD_MAX_MB")
        or os.getenv("MAX_UPLOAD_MB")
        or str(_DEFAULT_LOCAL_AUDIO_UPLOAD_MAX_MB)
    )
    try:
        max_mb = max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        max_mb = _DEFAULT_LOCAL_AUDIO_UPLOAD_MAX_MB
    return max_mb * 1024 * 1024


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
    if not _has_uploaded_audio(get_job_files(job_id)):
        raise invalid_step_state("音频尚未上传完成，请稍后重试")
    consume_test_credit(job_id)
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
        "audio OSS upload ready job=%s object_key=%s",
        job_id,
        normalized_object_key,
    )
    return {"object_key": normalized_object_key}


def mark_audio_local_ready(job_id: str, audio_path: str) -> dict:
    normalized_audio_path = str(audio_path or "").strip()
    if not normalized_audio_path:
        raise invalid_step_state("本地音频上传失败，请重试")
    upsert_job_files(
        job_id,
        audio_path=normalized_audio_path,
        asr_oss_key=None,
        pending_asr_oss_key=None,
    )
    update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    logging.info(
        "local audio upload ready job=%s audio_path=%s",
        job_id,
        normalized_audio_path,
    )
    return {"audio_path": normalized_audio_path}


def save_local_uploaded_audio(job_id: str, audio_file: UploadFile) -> dict[str, Any]:
    dirs = ensure_job_dirs(job_id)
    raw_name = Path(audio_file.filename or "audio.mp3").name
    suffix = Path(raw_name).suffix.lower() or ".mp3"
    audio_path = dirs["input"] / f"audio{suffix}"
    validate_audio_extension(audio_path)

    max_bytes = _local_audio_upload_max_bytes()
    total = 0
    try:
        with audio_path.open("wb") as output:
            while True:
                chunk = audio_file.file.read(_LOCAL_AUDIO_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise upload_too_large(f"文件超过 {max_bytes // (1024 * 1024)}MB，请压缩后重试")
                output.write(chunk)
    except Exception:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    if total <= 0:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise invalid_step_state("上传文件为空")

    ready = mark_audio_local_ready(job_id, str(audio_path))
    return {
        **ready,
        "filename": raw_name,
        "stored_as": audio_path.name,
        "size_bytes": total,
    }


def save_local_uploaded_video(job_id: str, source_file: UploadFile) -> dict[str, Any]:
    raw_name = Path(source_file.filename or "source.mp4").name
    suffix = Path(raw_name).suffix.lower() or ".mp4"
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise invalid_step_state("当前文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。")

    total = 0
    while True:
        chunk = source_file.file.read(_LOCAL_AUDIO_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)

    if total <= 0:
        raise invalid_step_state("上传文件为空")

    upsert_job_files(
        job_id,
        video_path=None,
        source_file_name=raw_name,
        source_file_type=str(source_file.content_type or "").strip() or None,
        source_file_size_bytes=total,
    )
    if _has_uploaded_audio(get_job_files(job_id)):
        update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    return {
        "video_path": None,
        "filename": raw_name,
        "stored_as": None,
        "size_bytes": total,
    }


def save_source_video_metadata(
    job_id: str,
    *,
    width: int,
    height: int,
    fps: float | None = None,
    duration_sec: float | None = None,
    file_name: str = "",
    file_type: str = "",
    file_size_bytes: int = 0,
) -> dict[str, Any]:
    normalized_width = int(width)
    normalized_height = int(height)
    if normalized_width <= 0 or normalized_height <= 0:
        raise invalid_step_state("无法读取源视频分辨率，请重新选择文件后重试")

    normalized_fps = float(fps) if fps is not None else None
    if normalized_fps is not None and normalized_fps <= 0:
        normalized_fps = None
    normalized_duration = float(duration_sec) if duration_sec is not None else None
    if normalized_duration is not None and normalized_duration <= 0:
        normalized_duration = None

    payload = {
        "source_width": normalized_width,
        "source_height": normalized_height,
        "source_fps": normalized_fps,
        "source_duration_sec": normalized_duration,
        "source_file_name": str(file_name or "").strip() or None,
        "source_file_type": str(file_type or "").strip() or None,
        "source_file_size_bytes": max(0, int(file_size_bytes or 0)) or None,
    }
    upsert_job_files(job_id, video_path=None, **payload)
    if _has_uploaded_audio(get_job_files(job_id)):
        update_job(job_id, status=JOB_STATUS_UPLOAD_READY, progress=PROGRESS_UPLOAD_READY)
    return payload
