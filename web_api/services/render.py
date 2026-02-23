from __future__ import annotations

from pathlib import Path

from video_auto_cut.orchestration.pipeline_service import run_render as run_render_stage

from ..config import ensure_job_dirs
from ..constants import JOB_STATUS_SUCCEEDED, PROGRESS_SUCCEEDED
from ..repository import get_job_files, update_job, upsert_job_files
from .pipeline_options import build_pipeline_options


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
    run_render_stage(Path(video_path), Path(step1_srt_path), options)
    if not output_path.exists():
        raise RuntimeError("render output missing")

    upsert_job_files(job_id, final_video_path=str(output_path))
    update_job(job_id, status=JOB_STATUS_SUCCEEDED, progress=PROGRESS_SUCCEEDED)
