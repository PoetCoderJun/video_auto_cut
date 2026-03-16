from __future__ import annotations

from ..constants import JOB_STATUS_SUCCEEDED, PROGRESS_SUCCEEDED
from ..repository import consume_job_export_credit, get_job_owner_user_id, update_job


def mark_render_success(job_id: str) -> dict[str, int | bool]:
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise RuntimeError("job owner not found")

    try:
        billing = consume_job_export_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise RuntimeError("额度不足，请先兑换邀请码后重试") from exc
        raise

    update_job(
        job_id,
        status=JOB_STATUS_SUCCEEDED,
        progress=PROGRESS_SUCCEEDED,
        stage_code="EXPORT_SUCCEEDED",
        stage_message="视频导出成功。",
    )
    return {
        "consumed": bool(billing["consumed"]),
        "balance": int(billing["balance"]),
    }
