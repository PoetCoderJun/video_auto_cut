"""Generate OSS presigned URLs for direct client upload."""

from __future__ import annotations

from video_auto_cut.asr.oss_uploader import OSSAudioUploader

from ..config import get_settings


def get_oss_uploader() -> OSSAudioUploader:
    settings = get_settings()
    if not settings.asr_oss_endpoint or not settings.asr_oss_bucket:
        raise RuntimeError("OSS not configured: ASR_OSS_ENDPOINT and ASR_OSS_BUCKET required")
    if not settings.asr_oss_access_key_id or not settings.asr_oss_access_key_secret:
        raise RuntimeError("OSS credentials missing: ASR_OSS_ACCESS_KEY_ID and ASR_OSS_ACCESS_KEY_SECRET required")
    return OSSAudioUploader(
        endpoint=settings.asr_oss_endpoint,
        bucket_name=settings.asr_oss_bucket,
        access_key_id=settings.asr_oss_access_key_id,
        access_key_secret=settings.asr_oss_access_key_secret,
        prefix=(settings.asr_oss_prefix or "video-auto-cut/asr").strip().strip("/") or "video-auto-cut/asr",
        signed_url_ttl_seconds=int(settings.asr_oss_signed_url_ttl_seconds),
    )


def get_presigned_put_url_for_job(
    job_id: str, *, expires: int = 3600, suffix: str = ".wav"
) -> tuple[str, str]:
    """Return (put_url, object_key) for client direct upload. suffix: .wav or .mp3."""
    uploader = get_oss_uploader()
    object_key = uploader.build_object_key_for_job(job_id, suffix=suffix)
    put_url = uploader.get_presigned_put_url(object_key, expires=expires)
    return put_url, object_key
