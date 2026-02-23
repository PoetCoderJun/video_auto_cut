from __future__ import annotations

import logging

from ..constants import (
    JOB_STATUS_FAILED,
    JOB_STATUS_RENDER_RUNNING,
    JOB_STATUS_STEP1_RUNNING,
    JOB_STATUS_STEP2_RUNNING,
    PROGRESS_STEP2_RUNNING,
    PROGRESS_RENDER_RUNNING,
    PROGRESS_STEP1_RUNNING,
    TASK_TYPE_RENDER,
    TASK_TYPE_STEP1,
    TASK_TYPE_STEP2,
)
from ..repository import enqueue_task, has_pending_task, set_task_failed, set_task_succeeded, update_job
from .render import run_render
from .step1 import run_step1
from .step2 import run_step2


TASK_DISPATCH = {
    TASK_TYPE_STEP1: run_step1,
    TASK_TYPE_STEP2: run_step2,
    TASK_TYPE_RENDER: run_render,
}


def queue_job_task(job_id: str, task_type: str) -> int:
    if has_pending_task(job_id):
        raise RuntimeError("task already running")

    if task_type == TASK_TYPE_STEP1:
        update_job(job_id, status=JOB_STATUS_STEP1_RUNNING, progress=PROGRESS_STEP1_RUNNING)
    elif task_type == TASK_TYPE_STEP2:
        update_job(job_id, status=JOB_STATUS_STEP2_RUNNING, progress=PROGRESS_STEP2_RUNNING)
    elif task_type == TASK_TYPE_RENDER:
        update_job(job_id, status=JOB_STATUS_RENDER_RUNNING, progress=PROGRESS_RENDER_RUNNING)
    else:
        raise RuntimeError(f"unsupported task type: {task_type}")

    return enqueue_task(job_id, task_type, payload={})


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
        update_job(
            job_id,
            status=JOB_STATUS_FAILED,
            error_code="INTERNAL_ERROR",
            error_message=str(exc),
        )
        return

    set_task_succeeded(task_id)
