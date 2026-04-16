from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ensure_job_dirs, get_settings, job_dir
from .constants import (
    ALLOWED_VIDEO_EXTENSIONS,
    JOB_ERROR_CODE_FILES_MISSING,
    JOB_ERROR_MESSAGE_FILES_MISSING,
    JOB_STATUS_CREATED,
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_UPLOAD_READY,
)
from .utils.persistence_helpers import now_iso, parse_iso_datetime_or_epoch
from video_auto_cut.shared.test_text_io import (
    load_test_chapters,
    load_test_lines,
    write_test_json,
    write_topics_json,
)

USER_STATUS_PENDING_COUPON = "PENDING_COUPON"
USER_STATUS_ACTIVE = "ACTIVE"
_STAGE_UNSET = object()

JOB_FILE_FIELDS = (
    "video_path",
    "audio_path",
    "asr_oss_key",
    "pending_asr_oss_key",
    "optimized_srt_oss_key",
    "optimized_srt_oss_signed_url",
    "srt_path",
    "optimized_srt_path",
    "chapters_draft_path",
    "final_test_text_path",
    "final_test_srt_path",
    "final_chapters_path",
    "final_video_path",
)

_STATUS_RANK = {
    JOB_STATUS_CREATED: 0,
    JOB_STATUS_UPLOAD_READY: 1,
    JOB_STATUS_TEST_RUNNING: 2,
    JOB_STATUS_TEST_READY: 3,
    JOB_STATUS_TEST_CONFIRMED: 4,
    JOB_STATUS_SUCCEEDED: 5,
    JOB_STATUS_FAILED: 6,
}

def _parse_iso(value: str | None) -> datetime:
    return parse_iso_datetime_or_epoch(value)

def _meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.meta.json"


def _files_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.files.json"


def _error_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.error.json"


def _test_confirmed_path(job_id: str) -> Path:
    return job_dir(job_id) / "test" / ".confirmed"


def _render_succeeded_path(job_id: str) -> Path:
    return job_dir(job_id) / "render" / ".succeeded"


def _test_lines_draft_path(job_id: str) -> Path:
    return job_dir(job_id) / "test" / "lines_draft.json"


def _test_chapters_draft_path(job_id: str) -> Path:
    return job_dir(job_id) / "test" / "chapters_draft.json"


def _test_final_lines_path(job_id: str) -> Path:
    return job_dir(job_id) / "test" / "final_test.json"


def _test_final_chapters_path(job_id: str) -> Path:
    return job_dir(job_id) / "test" / "final_chapters.json"


def _existing_test_lines_path(job_id: str, *, final: bool) -> Path:
    return _test_final_lines_path(job_id) if final else _test_lines_draft_path(job_id)


def _existing_test_chapters_path(job_id: str, *, final: bool) -> Path:
    return _test_final_chapters_path(job_id) if final else _test_chapters_draft_path(job_id)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_meta(job_id: str) -> dict[str, Any] | None:
    meta = _read_json(_meta_path(job_id))
    if isinstance(meta, dict):
        return meta
    return None


def _read_files_manifest(job_id: str) -> dict[str, Any]:
    payload = _read_json(_files_path(job_id))
    if isinstance(payload, dict):
        return payload
    return {}


def _write_files_manifest(job_id: str, payload: dict[str, Any]) -> None:
    _write_json(_files_path(job_id), payload)


def _existing_video_path(job_id: str) -> str | None:
    input_dir = job_dir(job_id) / "input"
    if not input_dir.exists():
        return None
    files = [
        item
        for item in input_dir.iterdir()
        if item.is_file()
        and not item.name.startswith(".")
        and item.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS
    ]
    if not files:
        return None
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return str(files[0])

def _existing_audio_path(job_id: str) -> str | None:
    input_dir = job_dir(job_id) / "input"
    if not input_dir.exists():
        return None
    candidates = [item for item in input_dir.iterdir() if item.is_file() and item.name.startswith("audio.")]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return str(candidates[0])


def _normalize_files(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"job_id": job_id}
    for field in JOB_FILE_FIELDS:
        raw = payload.get(field)
        if field in {
            "asr_oss_key",
            "pending_asr_oss_key",
            "optimized_srt_oss_key",
            "optimized_srt_oss_signed_url",
        }:
            result[field] = raw if isinstance(raw, str) and raw.strip() else None
        elif isinstance(raw, str) and raw.strip() and Path(raw).exists():
            result[field] = raw
        else:
            result[field] = None

    # Fallbacks by conventional paths.
    if not result["video_path"]:
        result["video_path"] = _existing_video_path(job_id)
    if not result["audio_path"]:
        result["audio_path"] = _existing_audio_path(job_id)

    test_srt = job_dir(job_id) / "test" / "final_test.srt"
    if test_srt.exists():
        result["final_test_srt_path"] = str(test_srt)

    chapters_draft = _existing_test_chapters_path(job_id, final=False)
    if chapters_draft.exists():
        result["chapters_draft_path"] = str(chapters_draft)

    final_test_text = _existing_test_lines_path(job_id, final=True)
    if final_test_text.exists():
        result["final_test_text_path"] = str(final_test_text)

    final_chapters = _existing_test_chapters_path(job_id, final=True)
    if final_chapters.exists():
        result["final_chapters_path"] = str(final_chapters)

    final_video = job_dir(job_id) / "render" / "output.mp4"
    if final_video.exists():
        result["final_video_path"] = str(final_video)

    return result


def _infer_job_status(job_id: str) -> str:
    files = _normalize_files(job_id, _read_files_manifest(job_id))
    if _error_path(job_id).exists():
        return JOB_STATUS_FAILED
    if _render_succeeded_path(job_id).exists():
        return JOB_STATUS_SUCCEEDED
    if files.get("final_video_path"):
        return JOB_STATUS_SUCCEEDED
    if (
        _test_confirmed_path(job_id).exists()
        and files.get("final_test_text_path")
        and files.get("final_test_srt_path")
        and files.get("final_chapters_path")
    ):
        return JOB_STATUS_TEST_CONFIRMED
    if (
        _existing_test_lines_path(job_id, final=False).exists()
        and _existing_test_chapters_path(job_id, final=False).exists()
    ):
        return JOB_STATUS_TEST_READY
    if files.get("video_path") or files.get("audio_path") or files.get("asr_oss_key"):
        return JOB_STATUS_UPLOAD_READY
    return JOB_STATUS_CREATED


def _progress_for_status(status: str) -> int:
    mapping = {
        JOB_STATUS_CREATED: 0,
        JOB_STATUS_UPLOAD_READY: 10,
        JOB_STATUS_TEST_RUNNING: 30,
        JOB_STATUS_TEST_READY: 35,
        JOB_STATUS_TEST_CONFIRMED: 45,
        JOB_STATUS_SUCCEEDED: 100,
        JOB_STATUS_FAILED: 0,
    }
    return int(mapping.get(status, 0))


def _normalize_meta_status(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    allowed = {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_TEST_RUNNING,
        JOB_STATUS_TEST_READY,
        JOB_STATUS_TEST_CONFIRMED,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }
    return raw if raw in allowed else None


def _effective_status(meta_status: str | None, inferred_status: str) -> str:
    if meta_status == JOB_STATUS_TEST_RUNNING and inferred_status in {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_TEST_READY,
    }:
        return JOB_STATUS_TEST_RUNNING
    if meta_status == JOB_STATUS_FAILED:
        return JOB_STATUS_FAILED
    if (
        meta_status is not None
        and _STATUS_RANK.get(meta_status, -1) > _STATUS_RANK.get(inferred_status, -1)
    ):
        return meta_status
    return inferred_status


def _missing_job_artifact_error(job_id: str, status: str, files: dict[str, Any]) -> dict[str, str] | None:
    if status in {JOB_STATUS_CREATED, JOB_STATUS_FAILED}:
        return None

    if status in {JOB_STATUS_UPLOAD_READY, JOB_STATUS_TEST_RUNNING}:
        if files.get("audio_path") or files.get("asr_oss_key"):
            return None
        return {
            "code": JOB_ERROR_CODE_FILES_MISSING,
            "message": JOB_ERROR_MESSAGE_FILES_MISSING,
        }

    if status == JOB_STATUS_TEST_READY:
        if (
            _existing_test_lines_path(job_id, final=False).exists()
            and _existing_test_chapters_path(job_id, final=False).exists()
        ):
            return None
        return {
            "code": JOB_ERROR_CODE_FILES_MISSING,
            "message": JOB_ERROR_MESSAGE_FILES_MISSING,
        }

    if status == JOB_STATUS_TEST_CONFIRMED:
        if (
            files.get("final_test_text_path")
            and files.get("final_test_srt_path")
            and files.get("final_chapters_path")
            and _test_confirmed_path(job_id).exists()
        ):
            return None
        return {
            "code": JOB_ERROR_CODE_FILES_MISSING,
            "message": JOB_ERROR_MESSAGE_FILES_MISSING,
        }

    if status == JOB_STATUS_SUCCEEDED:
        return None

    return None


def create_job(job_id: str, status: str, owner_user_id: str) -> dict[str, Any]:
    normalized_status = _normalize_meta_status(status) or JOB_STATUS_CREATED
    now = now_iso()
    ensure_job_dirs(job_id)
    _write_json(
        _meta_path(job_id),
        {
            "job_id": job_id,
            "owner_user_id": owner_user_id,
            "status": normalized_status,
            "progress": _progress_for_status(normalized_status),
            "stage_code": None,
            "stage_message": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    _write_files_manifest(job_id, {})
    _error_path(job_id).unlink(missing_ok=True)
    _test_confirmed_path(job_id).unlink(missing_ok=True)
    _render_succeeded_path(job_id).unlink(missing_ok=True)
    return get_job(job_id, owner_user_id=owner_user_id) or {
        "job_id": job_id,
        "status": JOB_STATUS_CREATED,
        "progress": 0,
        "stage": None,
        "error": None,
    }


def get_job(job_id: str, *, owner_user_id: str | None = None) -> dict[str, Any] | None:
    meta = _read_meta(job_id)
    if not meta:
        return None
    if owner_user_id and str(meta.get("owner_user_id") or "") != owner_user_id:
        return None

    files = _normalize_files(job_id, _read_files_manifest(job_id))
    inferred_status = _infer_job_status(job_id)
    meta_status = _normalize_meta_status(meta.get("status"))
    status = _effective_status(meta_status, inferred_status)
    meta_progress = meta.get("progress")
    try:
        progress_from_meta = int(meta_progress) if meta_progress is not None else None
    except Exception:
        progress_from_meta = None
    progress = _progress_for_status(status)
    if meta_status == status and progress_from_meta is not None:
        progress = max(0, min(100, progress_from_meta))
    error_payload = _read_json(_error_path(job_id))
    error: dict[str, str] | None = None
    if isinstance(error_payload, dict):
        code = str(error_payload.get("code") or "").strip()
        message = str(error_payload.get("message") or "").strip()
        if code:
            error = {"code": code, "message": message}
    if error is None:
        synthesized_error = _missing_job_artifact_error(job_id, status, files)
        if synthesized_error is not None:
            status = JOB_STATUS_FAILED
            error = synthesized_error

    stage_code = str(meta.get("stage_code") or "").strip()
    stage_message = str(meta.get("stage_message") or "").strip()
    stage: dict[str, str] | None = None
    if stage_code or stage_message:
        stage = {
            "code": stage_code or "UNKNOWN_STAGE",
            "message": stage_message,
        }
    if status == JOB_STATUS_FAILED:
        stage = None

    return {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "stage": stage,
        "error": error,
    }


def get_job_owner_user_id(job_id: str) -> str | None:
    meta = _read_meta(job_id)
    if not isinstance(meta, dict):
        return None
    owner_user_id = str(meta.get("owner_user_id") or "").strip()
    return owner_user_id or None


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    stage_code: object = _STAGE_UNSET,
    stage_message: object = _STAGE_UNSET,
) -> None:
    meta = _read_meta(job_id)
    if not meta:
        return

    normalized_status = _normalize_meta_status(status)
    if normalized_status:
        meta["status"] = normalized_status
    if progress is not None:
        try:
            meta["progress"] = max(0, min(100, int(progress)))
        except Exception:
            pass

    if stage_code is not _STAGE_UNSET or stage_message is not _STAGE_UNSET:
        resolved_stage_code = "" if stage_code is _STAGE_UNSET else str(stage_code or "").strip()
        resolved_stage_message = "" if stage_message is _STAGE_UNSET else str(stage_message or "").strip()
        meta["stage_code"] = resolved_stage_code or None
        meta["stage_message"] = resolved_stage_message or None

    meta["updated_at"] = now_iso()
    _write_json(_meta_path(job_id), meta)

    if normalized_status == JOB_STATUS_TEST_CONFIRMED:
        _test_confirmed_path(job_id).parent.mkdir(parents=True, exist_ok=True)
        _test_confirmed_path(job_id).touch()
    elif normalized_status == JOB_STATUS_SUCCEEDED:
        _render_succeeded_path(job_id).parent.mkdir(parents=True, exist_ok=True)
        _render_succeeded_path(job_id).touch()
    elif normalized_status == JOB_STATUS_FAILED and error_code:
        _write_json(
            _error_path(job_id),
            {
                "code": str(error_code),
                "message": str(error_message or ""),
            },
        )
    elif normalized_status in {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_TEST_RUNNING,
        JOB_STATUS_TEST_READY,
        JOB_STATUS_TEST_CONFIRMED,
        JOB_STATUS_SUCCEEDED,
    }:
        _error_path(job_id).unlink(missing_ok=True)

    if normalized_status in {
        JOB_STATUS_CREATED,
        JOB_STATUS_TEST_READY,
        JOB_STATUS_TEST_CONFIRMED,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    } and stage_code is _STAGE_UNSET and stage_message is _STAGE_UNSET:
        meta["stage_code"] = None
        meta["stage_message"] = None
        meta["updated_at"] = now_iso()
        _write_json(_meta_path(job_id), meta)


def touch_job(job_id: str) -> None:
    meta = _read_meta(job_id)
    if not meta:
        return
    meta["updated_at"] = now_iso()
    _write_json(_meta_path(job_id), meta)


def get_job_files(job_id: str) -> dict[str, Any] | None:
    if not _meta_path(job_id).exists():
        return None
    return _normalize_files(job_id, _read_files_manifest(job_id))


def upsert_job_files(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    if not _meta_path(job_id).exists():
        return
    payload = _read_files_manifest(job_id)
    for field in JOB_FILE_FIELDS:
        if field in kwargs:
            value = kwargs[field]
            payload[field] = str(value) if isinstance(value, Path) else value
    _write_files_manifest(job_id, payload)
    touch_job(job_id)


def clear_step_data(job_id: str) -> None:
    _test_lines_draft_path(job_id).unlink(missing_ok=True)
    _test_chapters_draft_path(job_id).unlink(missing_ok=True)
    _test_final_lines_path(job_id).unlink(missing_ok=True)
    _test_final_chapters_path(job_id).unlink(missing_ok=True)
    _test_confirmed_path(job_id).unlink(missing_ok=True)


def _has_artifacts(files: dict[str, Any]) -> bool:
    for field in JOB_FILE_FIELDS:
        if field == "pending_asr_oss_key":
            continue
        value = files.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _is_cleanup_candidate_status(status: str | None) -> bool:
    return status == JOB_STATUS_SUCCEEDED


def _list_succeeded_jobs_with_artifacts(
    *,
    limit: int,
    cutoff_updated_at: str | None = None,
) -> list[str]:
    settings = get_settings()
    jobs_root = settings.work_dir / "jobs"
    if not jobs_root.exists():
        return []

    cutoff = _parse_iso(cutoff_updated_at) if cutoff_updated_at is not None else None
    pairs: list[tuple[datetime, str]] = []
    for item in jobs_root.iterdir():
        if not item.is_dir():
            continue
        job_id = item.name
        meta = _read_meta(job_id)
        if not meta:
            continue
        status = _normalize_meta_status(meta.get("status"))
        if not _is_cleanup_candidate_status(status):
            continue
        files = get_job_files(job_id) or {}
        if not _has_artifacts(files):
            continue
        updated_at = _parse_iso(str(meta.get("updated_at") or meta.get("created_at") or ""))
        if cutoff is not None and updated_at > cutoff:
            continue
        pairs.append((updated_at, job_id))

    pairs.sort(key=lambda pair: pair[0])
    return [job_id for _, job_id in pairs[: int(max(1, limit))]]


def list_expired_succeeded_jobs(cutoff_updated_at: str, *, limit: int) -> list[str]:
    return _list_succeeded_jobs_with_artifacts(limit=limit, cutoff_updated_at=cutoff_updated_at)


def list_succeeded_jobs_with_artifacts(*, limit: int) -> list[str]:
    return _list_succeeded_jobs_with_artifacts(limit=limit)


def list_jobs_by_status(status: str) -> list[str]:
    normalized_status = _normalize_meta_status(status)
    if normalized_status is None:
        return []

    settings = get_settings()
    jobs_root = settings.work_dir / "jobs"
    if not jobs_root.exists():
        return []

    job_ids: list[str] = []
    for item in sorted(path for path in jobs_root.iterdir() if path.is_dir() and path.name.startswith("job_")):
        meta = _read_meta(item.name)
        if not meta:
            continue
        if _normalize_meta_status(meta.get("status")) == normalized_status:
            job_ids.append(item.name)
    return job_ids


def replace_test_lines(job_id: str, lines: list[dict[str, Any]]) -> None:
    write_test_json(lines, _test_lines_draft_path(job_id))


def list_test_lines(job_id: str) -> list[dict[str, Any]]:
    final_path = _existing_test_lines_path(job_id, final=True)
    draft_path = _existing_test_lines_path(job_id, final=False)
    path = final_path if _test_confirmed_path(job_id).exists() and final_path.exists() else draft_path
    if not path.exists():
        path = final_path
    if not path.exists():
        return []
    return load_test_lines(path)


def replace_test_chapters(job_id: str, chapters: list[dict[str, Any]]) -> None:
    write_topics_json(chapters, _test_chapters_draft_path(job_id))


def _list_test_chapters_from_path(job_id: str, path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = list_test_lines(job_id)
    kept_lines = [line for line in lines if not bool(line.get("user_final_remove", False))]
    return load_test_chapters(path, kept_lines=kept_lines)


def list_test_chapters(job_id: str) -> list[dict[str, Any]]:
    final_path = _existing_test_chapters_path(job_id, final=True)
    if _test_confirmed_path(job_id).exists() and final_path.exists():
        return list_final_test_chapters(job_id)
    draft_path = _existing_test_chapters_path(job_id, final=False)
    if draft_path.exists():
        return _list_test_chapters_from_path(job_id, draft_path)
    return list_final_test_chapters(job_id)


def list_final_test_chapters(job_id: str) -> list[dict[str, Any]]:
    return _list_test_chapters_from_path(
        job_id,
        _existing_test_chapters_path(job_id, final=True),
    )
