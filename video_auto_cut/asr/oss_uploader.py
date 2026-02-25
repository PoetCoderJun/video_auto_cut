from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UploadedAudioObject:
    object_key: str
    signed_url: str
    size_bytes: int


class OSSAudioUploader:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket_name: str,
        access_key_id: str,
        access_key_secret: str,
        prefix: str,
        signed_url_ttl_seconds: int,
    ) -> None:
        try:
            import oss2  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency `oss2`. Please install with `pip install oss2`."
            ) from exc

        endpoint = (endpoint or "").strip()
        bucket_name = _normalize_bucket_name((bucket_name or "").strip())
        access_key_id = (access_key_id or "").strip()
        access_key_secret = (access_key_secret or "").strip()
        prefix = (prefix or "video-auto-cut/asr").strip().strip("/")
        if not endpoint or not bucket_name or not access_key_id or not access_key_secret:
            raise RuntimeError("OSS config missing: endpoint/bucket/access_key_id/access_key_secret")

        endpoint = _ensure_https_endpoint(endpoint)
        self._prefix = prefix
        self._signed_url_ttl_seconds = int(max(60, signed_url_ttl_seconds))
        auth = oss2.Auth(access_key_id, access_key_secret)
        self._bucket = oss2.Bucket(auth, endpoint, bucket_name)

    def upload_audio(self, local_path: Path) -> UploadedAudioObject:
        path = Path(local_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"audio file not found: {path}")

        object_key = self._build_object_key(path)
        self._bucket.put_object_from_file(object_key, str(path))
        signed_url = self._bucket.sign_url(
            "GET",
            object_key,
            self._signed_url_ttl_seconds,
            slash_safe=True,
        )
        if signed_url.startswith("http://"):
            signed_url = "https://" + signed_url[len("http://") :]
        return UploadedAudioObject(
            object_key=object_key,
            signed_url=signed_url,
            size_bytes=int(path.stat().st_size),
        )

    def _build_object_key(self, path: Path) -> str:
        stamp = dt.datetime.utcnow().strftime("%Y%m%d/%H%M%S")
        job_id = _guess_job_id(path)
        stem = _sanitize(path.stem)[:32] or "audio"
        suffix = path.suffix.lower() or ".wav"
        nonce = uuid.uuid4().hex[:10]
        parts = [self._prefix]
        if job_id:
            parts.append(job_id)
        parts.append(stamp)
        return "/".join(part for part in parts if part) + f"/{stem}_{nonce}{suffix}"


def _ensure_https_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()
    if normalized.startswith("https://"):
        return normalized
    if normalized.startswith("http://"):
        return "https://" + normalized[len("http://") :]
    return "https://" + normalized


def _normalize_bucket_name(bucket_name: str) -> str:
    raw = bucket_name.strip()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    marker = ".oss-"
    if marker in raw:
        raw = raw.split(marker, 1)[0]
    return raw.strip(".")


def _guess_job_id(path: Path) -> str:
    for item in path.parts:
        if item.startswith("job_"):
            return _sanitize(item)[:40]
    return ""


def _sanitize(text: str) -> str:
    return "".join(ch for ch in str(text) if ch.isalnum() or ch in {"-", "_"})
