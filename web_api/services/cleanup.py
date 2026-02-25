from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..config import get_settings, job_dir
from ..constants import JOB_STATUS_SUCCEEDED, PROGRESS_SUCCEEDED
from ..repository import (
    clear_step_data,
    get_job_files,
    list_expired_succeeded_jobs,
    list_succeeded_jobs_with_artifacts,
    touch_job,
    update_job,
    upsert_job_files,
)

ARTIFACT_FIELDS = (
    "video_path",
    "srt_path",
    "optimized_srt_path",
    "final_step1_srt_path",
    "topics_path",
    "final_topics_path",
    "final_video_path",
)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_within(base_dir: Path, target: Path) -> bool:
    base = base_dir.resolve()
    candidate = target.resolve(strict=False)
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _collect_artifact_paths(job_id: str, files: dict[str, object]) -> list[Path]:
    settings = get_settings()
    paths: list[Path] = []

    for field in ARTIFACT_FIELDS:
        raw = files.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = Path(raw).expanduser()
        if _is_within(settings.work_dir, candidate):
            paths.append(candidate)
        else:
            logging.warning(
                "[web_api] skip cleanup path outside workdir job=%s field=%s path=%s",
                job_id,
                field,
                candidate,
            )

    job_base = job_dir(job_id)
    if _is_within(settings.work_dir, job_base):
        paths.append(job_base)
    return paths


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in sorted(paths, key=lambda p: len(p.resolve(strict=False).parts), reverse=True):
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return True
    path.unlink(missing_ok=True)
    return True


def _list_orphan_job_dirs(*, older_than: datetime | None = None) -> list[Path]:
    settings = get_settings()
    jobs_root = settings.work_dir / "jobs"
    if not jobs_root.exists():
        return []

    result: list[Path] = []
    for item in jobs_root.iterdir():
        if not item.is_dir() or not item.name.startswith("job_"):
            continue
        if (item / "job.meta.json").exists():
            continue
        if older_than is not None:
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime > older_than:
                continue
        result.append(item)
    result.sort(key=lambda p: p.name)
    return result


def cleanup_orphan_job_dirs(
    *,
    older_than: datetime | None,
    limit: int | None,
    reason: str,
) -> int:
    candidates = _list_orphan_job_dirs(older_than=older_than)
    if limit is not None:
        capped = max(1, int(limit))
        candidates = candidates[:capped]

    removed = 0
    for path in candidates:
        try:
            if _remove_path(path):
                removed += 1
        except Exception:
            logging.exception("[web_api] orphan cleanup failed path=%s", path)

    if removed:
        logging.info("[web_api] orphan cleanup completed reason=%s removed_dirs=%s", reason, removed)
    return removed


def cleanup_job_artifacts(job_id: str, *, reason: str) -> int:
    files = get_job_files(job_id)
    if not files:
        return 0

    removed = 0
    for path in _dedupe_paths(_collect_artifact_paths(job_id, files)):
        try:
            if _remove_path(path):
                removed += 1
        except Exception:
            logging.exception("[web_api] cleanup failed removing path job=%s path=%s", job_id, path)

    clear_step_data(job_id)
    upsert_job_files(
        job_id,
        video_path=None,
        srt_path=None,
        optimized_srt_path=None,
        final_step1_srt_path=None,
        topics_path=None,
        final_topics_path=None,
        final_video_path=None,
    )
    update_job(job_id, status=JOB_STATUS_SUCCEEDED, progress=PROGRESS_SUCCEEDED)
    logging.info("[web_api] cleaned artifacts job=%s reason=%s removed_paths=%s", job_id, reason, removed)
    return removed


def mark_job_cleanup_from_now(job_id: str, *, reason: str) -> None:
    settings = get_settings()
    if not settings.cleanup_enabled:
        return
    touch_job(job_id)
    logging.info(
        "[web_api] marked delayed cleanup job=%s reason=%s ttl_seconds=%s",
        job_id,
        reason,
        settings.cleanup_ttl_seconds,
    )


def cleanup_expired_jobs() -> int:
    settings = get_settings()
    if not settings.cleanup_enabled:
        return 0

    ttl_seconds = max(0, int(settings.cleanup_ttl_seconds))
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    cutoff_iso = _to_iso(cutoff)
    job_ids = list_expired_succeeded_jobs(cutoff_iso, limit=settings.cleanup_batch_size)

    cleaned = 0
    for job_id in job_ids:
        try:
            cleanup_job_artifacts(job_id, reason=f"ttl>{ttl_seconds}s")
            cleaned += 1
        except Exception:
            logging.exception("[web_api] cleanup failed job=%s", job_id)

    orphan_cleaned = cleanup_orphan_job_dirs(
        older_than=cutoff,
        limit=settings.cleanup_batch_size,
        reason=f"ttl>{ttl_seconds}s",
    )

    if cleaned or orphan_cleaned:
        logging.info(
            "[web_api] cleanup sweep completed cleaned_jobs=%s cleaned_orphans=%s cutoff=%s",
            cleaned,
            orphan_cleaned,
            cutoff_iso,
        )
    return cleaned + orphan_cleaned


def cleanup_on_startup() -> int:
    settings = get_settings()
    if not settings.cleanup_enabled or not settings.cleanup_on_startup:
        return 0

    total_cleaned = 0
    orphan_cleaned = cleanup_orphan_job_dirs(older_than=None, limit=None, reason="startup")
    while True:
        job_ids = list_succeeded_jobs_with_artifacts(limit=settings.cleanup_batch_size)
        if not job_ids:
            break
        for job_id in job_ids:
            try:
                cleanup_job_artifacts(job_id, reason="startup")
                total_cleaned += 1
            except Exception:
                logging.exception("[web_api] startup cleanup failed job=%s", job_id)

    if total_cleaned or orphan_cleaned:
        logging.info(
            "[web_api] startup cleanup completed cleaned_jobs=%s cleaned_orphans=%s",
            total_cleaned,
            orphan_cleaned,
        )
    return total_cleaned + orphan_cleaned
