from __future__ import annotations

import logging
from pathlib import Path

from video_auto_cut.orchestration.pipeline_service import run_auto_edit, run_transcribe

from ..config import ensure_job_dirs
from ..constants import (
    DEFAULT_ENCODING,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP1_READY,
    PROGRESS_STEP1_CONFIRMED,
    PROGRESS_STEP1_READY,
)
from ..repository import (
    consume_step1_credit,
    get_job_owner_user_id,
    replace_step1_lines,
    update_job,
    upsert_job_files,
)
from ..utils.srt_utils import (
    build_step1_lines_from_srts,
    write_final_step1_srt,
    write_step1_json,
)
from .pipeline_options import build_pipeline_options


def run_step1(job_id: str) -> None:
    dirs = ensure_job_dirs(job_id)
    files = _load_required_paths(job_id)
    video_path = Path(files["video_path"])
    options = build_pipeline_options()

    logging.info("[web_api] step1 transcribe start: %s", video_path)
    srt_path = run_transcribe(video_path, options)

    logging.info("[web_api] step1 auto-edit start: %s", srt_path)
    optimized_srt_path = run_auto_edit(srt_path, options)

    lines = build_step1_lines_from_srts(srt_path, optimized_srt_path, DEFAULT_ENCODING)
    if not lines:
        raise RuntimeError("step1 produced empty line list")

    final_step1_srt = dirs["step1"] / "final_step1.srt"
    final_step1_json = dirs["step1"] / "final_step1.json"
    write_final_step1_srt(lines, final_step1_srt, DEFAULT_ENCODING)
    write_step1_json(lines, final_step1_json)

    replace_step1_lines(job_id, lines)
    upsert_job_files(
        job_id,
        srt_path=str(srt_path),
        optimized_srt_path=str(optimized_srt_path),
        final_step1_srt_path=str(final_step1_srt),
    )

    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise RuntimeError("job owner not found")
    try:
        consume_step1_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise RuntimeError("额度不足，请先兑换邀请码后重试") from exc
        raise

    update_job(job_id, status=JOB_STATUS_STEP1_READY, progress=PROGRESS_STEP1_READY)


def _load_required_paths(job_id: str) -> dict[str, str]:
    from ..repository import get_job_files

    files = get_job_files(job_id)
    if not files:
        raise RuntimeError(f"job files not found: {job_id}")
    if not files.get("video_path"):
        raise RuntimeError("upload video missing for step1")
    return files


def confirm_step1(job_id: str, updates: list[dict[str, object]]) -> list[dict[str, object]]:
    from ..repository import list_step1_lines

    existing = list_step1_lines(job_id)
    if not existing:
        raise RuntimeError("step1 lines not found")

    by_id = {int(item["line_id"]): dict(item) for item in existing}
    for item in updates:
        line_id = int(item["line_id"])
        if line_id not in by_id:
            raise RuntimeError(f"invalid line_id: {line_id}")
        by_id[line_id]["optimized_text"] = str(item.get("optimized_text", "")).strip()
        by_id[line_id]["user_final_remove"] = bool(item.get("user_final_remove", False))

    lines = [by_id[key] for key in sorted(by_id)]
    replace_step1_lines(job_id, lines)

    dirs = ensure_job_dirs(job_id)
    final_step1_srt = dirs["step1"] / "final_step1.srt"
    final_step1_json = dirs["step1"] / "final_step1.json"
    write_final_step1_srt(lines, final_step1_srt, DEFAULT_ENCODING)
    write_step1_json(lines, final_step1_json)

    upsert_job_files(job_id, final_step1_srt_path=str(final_step1_srt))
    update_job(job_id, status=JOB_STATUS_STEP1_CONFIRMED, progress=PROGRESS_STEP1_CONFIRMED)
    return lines
