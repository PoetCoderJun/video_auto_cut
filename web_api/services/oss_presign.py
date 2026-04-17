"""Generate OSS presigned URLs for direct client upload."""

from __future__ import annotations

from video_auto_cut.asr.oss_uploader import OSSAudioUploader, create_oss_uploader_from_config

from ..config import get_settings


def get_oss_uploader() -> OSSAudioUploader:
    settings = get_settings()
    if not settings.asr_oss_endpoint or not settings.asr_oss_bucket:
        raise RuntimeError("OSS not configured: OSS_ENDPOINT and OSS_BUCKET required")
    if not settings.asr_oss_access_key_id or not settings.asr_oss_access_key_secret:
        raise RuntimeError("OSS credentials missing: OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET required")
    return create_oss_uploader_from_config(settings)


def get_presigned_put_url_for_job(
    job_id: str,
    *,
    expires: int = 3600,
    suffix: str = ".mp3",
    content_type: str = "audio/mpeg",
) -> tuple[str, str]:
    """Return (put_url, object_key) for client direct upload."""
    uploader = get_oss_uploader()
    object_key = uploader.build_object_key_for_job(job_id, suffix=suffix)
    put_url = uploader.get_presigned_put_url(
        object_key,
        expires=expires,
        content_type=content_type,
    )
    return put_url, object_key
