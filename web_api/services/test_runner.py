from __future__ import annotations

import json
import logging

from ..config import job_dir
from ..constants import (
    JOB_ERROR_CODE_FILES_MISSING,
    JOB_ERROR_MESSAGE_FILES_MISSING,
    JOB_STATUS_FAILED,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_TEST_READY,
    PROGRESS_UPLOAD_READY,
)
from ..job_file_repository import list_jobs_by_status, list_test_chapters, list_test_lines, update_job
from .test import run_test

_INTERRUPTED_STAGE_CODE = "TEST_RETRY_REQUIRED"
_INTERRUPTED_STAGE_MESSAGE = "服务重启后测试任务已中断，请重新开始字幕与章节生成。"
_RECOVERED_READY_STAGE_CODE = "TEST_READY"
_RECOVERED_READY_STAGE_MESSAGE = "检测到上次测试已生成字幕和章节，请确认内容。"


def _is_insufficient_credit_error(exc: Exception) -> bool:
    message = str(exc or "").strip()
    return "额度不足" in message


def _is_missing_job_file_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    if not message:
        return False
    return (
        "job files missing" in message
        or "job files not found" in message
        or "upload audio missing" in message
    )


def _public_task_error_code(exc: Exception) -> str:
    if _is_missing_job_file_error(exc):
        return JOB_ERROR_CODE_FILES_MISSING
    if _is_insufficient_credit_error(exc):
        return "INVALID_STEP_STATE"
    return "INTERNAL_ERROR"


def _public_task_error_message(exc: Exception) -> str:
    message = str(exc or "").strip()
    if _is_insufficient_credit_error(exc):
        return message or "额度不足，请先兑换邀请码后重试"
    if _is_missing_job_file_error(exc):
        return JOB_ERROR_MESSAGE_FILES_MISSING
    return "任务执行失败，请重试。"


def _exception_summary(exc: Exception) -> str:
    message = str(exc or "").strip()
    if not message:
        message = repr(exc)
    return f"{type(exc).__name__}: {message}"


def run_test_job_background(job_id: str) -> None:
    try:
        logging.info("[web_api] background test start job=%s", job_id)
        run_test(job_id)
    except Exception as exc:  # pragma: no cover - runtime behavior
        logging.error("[web_api] test flow failed summary job=%s error=%s", job_id, _exception_summary(exc))
        logging.exception("[web_api] background test failed job=%s", job_id)
        if _is_insufficient_credit_error(exc):
            update_job(
                job_id,
                status=JOB_STATUS_UPLOAD_READY,
                progress=PROGRESS_UPLOAD_READY,
            )
            return
        update_job(
            job_id,
            status=JOB_STATUS_FAILED,
            error_code=_public_task_error_code(exc),
            error_message=_public_task_error_message(exc),
        )


def _has_ready_test_drafts(job_id: str) -> bool:
    test_dir = job_dir(job_id) / "test"
    if not test_dir.exists():
        return False

    if not list_test_lines(job_id):
        return False

    draft_candidates = (
        test_dir / "chapters_draft.json",
        test_dir / "final_chapters.json",
    )
    if any(path.exists() for path in draft_candidates):
        return bool(list_test_chapters(job_id) or (test_dir / "chapters_draft.json").exists())
    return False


def recover_interrupted_test_runs() -> int:
    recovered = 0
    for job_id in list_jobs_by_status("TEST_RUNNING"):
        meta_path = job_dir(job_id) / "job.meta.json"
        if not meta_path.exists():
            continue
        try:
            status = str(json.loads(meta_path.read_text(encoding="utf-8")).get("status") or "").strip()
        except Exception:
            continue
        if status != "TEST_RUNNING":
            continue

        if _has_ready_test_drafts(job_id):
            update_job(
                job_id,
                status=JOB_STATUS_TEST_READY,
                progress=PROGRESS_TEST_READY,
                stage_code=_RECOVERED_READY_STAGE_CODE,
                stage_message=_RECOVERED_READY_STAGE_MESSAGE,
            )
        else:
            update_job(
                job_id,
                status=JOB_STATUS_UPLOAD_READY,
                progress=PROGRESS_UPLOAD_READY,
                stage_code=_INTERRUPTED_STAGE_CODE,
                stage_message=_INTERRUPTED_STAGE_MESSAGE,
            )
        recovered += 1

    if recovered:
        logging.warning("[web_api] recovered interrupted test runs count=%s", recovered)
    return recovered
