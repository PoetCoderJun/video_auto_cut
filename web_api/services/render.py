from __future__ import annotations

from pathlib import Path

from video_auto_cut.orchestration.pipeline_service import run_render as run_render_stage

from ..config import ensure_job_dirs
from ..constants import (
    JOB_STATUS_RENDER_RUNNING,
    JOB_STATUS_SUCCEEDED,
    PROGRESS_SUCCEEDED,
)
from ..repository import get_job_files, update_job, upsert_job_files
from .pipeline_options import build_pipeline_options


def _map_render_progress(stage: str, ratio: float | None) -> int:
    if stage == "node_render":
        if ratio is None:
            return 0
        return int(round(max(0.0, min(1.0, ratio)) * 99))
    if stage == "finalize":
        return 99
    # Before node-render begins, keep progress at 0% so UI strictly reflects frame progress.
    return 0


def run_render(job_id: str) -> None:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    video_path = files.get("video_path")
    step1_srt_path = files.get("final_step1_srt_path")
    if not video_path or not step1_srt_path:
        raise RuntimeError("render inputs missing")

    dirs = ensure_job_dirs(job_id)
    output_path = dirs["render"] / "output.mp4"
    cut_srt_path = dirs["render"] / "cut.srt"
    topics_path = files.get("final_topics_path")

    options = build_pipeline_options(
        render_output=str(output_path),
        render_cut_srt_output=str(cut_srt_path),
        render_topics=False,
        render_topics_input=str(topics_path) if topics_path else None,
    )

    last_progress = -1

    def push(progress: int) -> None:
        nonlocal last_progress
        value = max(last_progress, min(int(progress), 99))
        if value <= last_progress:
            return
        update_job(job_id, status=JOB_STATUS_RENDER_RUNNING, progress=value)
        last_progress = value

    def on_render_progress(stage: str, ratio: float | None) -> None:
        push(_map_render_progress(stage, ratio))

    push(0)
    run_render_stage(
        Path(video_path),
        Path(step1_srt_path),
        options,
        progress_callback=on_render_progress,
    )
    push(99)
    if not output_path.exists():
        raise RuntimeError("render output missing")

    upsert_job_files(job_id, final_video_path=str(output_path))
    update_job(job_id, status=JOB_STATUS_SUCCEEDED, progress=PROGRESS_SUCCEEDED)
