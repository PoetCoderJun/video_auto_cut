from __future__ import annotations

import logging

from ..constants import (
    JOB_STATUS_FAILED,
    JOB_STATUS_STEP1_RUNNING,
    JOB_STATUS_STEP2_RUNNING,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_UPLOAD_READY,
    PROGRESS_STEP2_RUNNING,
    PROGRESS_STEP1_RUNNING,
    TASK_TYPE_STEP1,
    TASK_TYPE_STEP2,
)
from ..repository import update_job
from ..task_queue import enqueue_task, get_queue_db_path, set_task_failed, set_task_succeeded
from .step1 import run_step1
from .step2 import run_step2


TASK_DISPATCH = {
    TASK_TYPE_STEP1: run_step1,
    TASK_TYPE_STEP2: run_step2,
}


def _is_insufficient_credit_error(exc: Exception) -> bool:
    message = str(exc or "").strip()
    return "额度不足" in message


def _public_task_error_message(exc: Exception) -> str:
    message = str(exc or "").strip()
    if _is_insufficient_credit_error(exc):
        return message or "额度不足，请先兑换邀请码后重试"
    return "任务执行失败，请重试。"


def queue_job_task(job_id: str, task_type: str) -> int:
    if task_type == TASK_TYPE_STEP1:
        status = JOB_STATUS_STEP1_RUNNING
        progress = PROGRESS_STEP1_RUNNING
    elif task_type == TASK_TYPE_STEP2:
        status = JOB_STATUS_STEP2_RUNNING
        progress = PROGRESS_STEP2_RUNNING
    else:
        raise RuntimeError(f"unsupported task type: {task_type}")

    task_id = enqueue_task(job_id, task_type, payload={})
    logging.info("[web_api] enqueued task_id=%s job_id=%s type=%s queue_path=%s", task_id, job_id, task_type, get_queue_db_path())
    update_job(job_id, status=status, progress=progress)
    return task_id


def execute_task(task: dict[str, object]) -> None:
    task_id = int(task["task_id"])
    job_id = str(task["job_id"])
    task_type = str(task["task_type"])

    fn = TASK_DISPATCH.get(task_type)
    if not fn:
        set_task_failed(task_id, f"unsupported task type: {task_type}")
        update_job(
            job_id,
            status=JOB_STATUS_FAILED,
            error_code="INTERNAL_ERROR",
            error_message="unsupported task",
        )
        return

    try:
        logging.info("[web_api] execute task=%s job=%s", task_type, job_id)
        fn(job_id)
    except Exception as exc:  # pragma: no cover - runtime behavior
        logging.exception("[web_api] task failed task=%s job=%s", task_type, job_id)
        set_task_failed(task_id, str(exc))
        if task_type == TASK_TYPE_STEP1 and _is_insufficient_credit_error(exc):
            update_job(
                job_id,
                status=JOB_STATUS_UPLOAD_READY,
                progress=PROGRESS_UPLOAD_READY,
                error_code="INVALID_STEP_STATE",
                error_message=_public_task_error_message(exc),
            )
            return
        update_job(
            job_id,
            status=JOB_STATUS_FAILED,
            error_code="INTERNAL_ERROR",
            error_message=_public_task_error_message(exc),
        )
        return

    set_task_succeeded(task_id)
