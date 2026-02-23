from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_auto_cut.orchestration.pipeline_service import (
    run_topic_segmentation_from_optimized_srt,
)

from ..config import ensure_job_dirs
from ..constants import (
    JOB_STATUS_STEP2_CONFIRMED,
    JOB_STATUS_STEP2_READY,
    PROGRESS_STEP2_CONFIRMED,
    PROGRESS_STEP2_READY,
)
from ..repository import (
    get_job_files,
    list_step2_chapters,
    replace_step2_chapters,
    update_job,
    upsert_job_files,
)
from .pipeline_options import build_pipeline_options
from ..utils.srt_utils import write_topics_json


def run_step2(job_id: str) -> None:
    files = get_job_files(job_id)
    if not files or not files.get("final_step1_srt_path"):
        raise RuntimeError("final_step1.srt missing for step2")

    dirs = ensure_job_dirs(job_id)
    source_srt = Path(files["final_step1_srt_path"])
    cut_srt = dirs["step2"] / "cut.srt"
    options = build_pipeline_options()
    generated_topics = dirs["step2"] / "topics.json"
    run_topic_segmentation_from_optimized_srt(
        optimized_srt_path=source_srt,
        cut_srt_output_path=cut_srt,
        topics_output_path=generated_topics,
        options=options,
    )

    chapters = _load_chapters(generated_topics)
    if not chapters:
        raise RuntimeError("step2 generated empty chapter list")

    final_topics = dirs["step2"] / "final_topics.json"
    replace_step2_chapters(job_id, chapters)
    write_topics_json(chapters, final_topics)

    upsert_job_files(
        job_id,
        topics_path=str(generated_topics),
        final_topics_path=str(final_topics),
    )
    update_job(job_id, status=JOB_STATUS_STEP2_READY, progress=PROGRESS_STEP2_READY)


def _load_chapters(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    topics = payload.get("topics")
    if not isinstance(topics, list):
        return []

    chapters: list[dict[str, Any]] = []
    for idx, topic in enumerate(topics, start=1):
        if not isinstance(topic, dict):
            continue
        try:
            start = float(topic.get("start", 0.0))
            end = float(topic.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue

        line_ids = topic.get("line_ids")
        if not isinstance(line_ids, list):
            line_ids = topic.get("segment_ids") if isinstance(topic.get("segment_ids"), list) else []

        chapters.append(
            {
                "chapter_id": idx,
                "title": str(topic.get("title") or f"章节{idx}"),
                "summary": str(topic.get("summary") or topic.get("title") or f"章节{idx}"),
                "start": start,
                "end": end,
                "line_ids": [int(item) for item in line_ids if isinstance(item, (int, float))],
            }
        )
    return chapters


def confirm_step2(job_id: str, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")

    normalized: list[dict[str, Any]] = []
    for idx, chapter in enumerate(chapters, start=1):
        start = float(chapter.get("start", 0.0))
        end = float(chapter.get("end", 0.0))
        if end <= start:
            raise RuntimeError(f"chapter range invalid: {idx}")
        line_ids_raw = chapter.get("line_ids") or []
        line_ids = [int(item) for item in line_ids_raw if isinstance(item, (int, float))]
        normalized.append(
            {
                "chapter_id": int(chapter.get("chapter_id", idx)),
                "title": str(chapter.get("title", "")).strip() or f"章节{idx}",
                "summary": str(chapter.get("summary", "")).strip(),
                "start": start,
                "end": end,
                "line_ids": line_ids,
            }
        )

    replace_step2_chapters(job_id, normalized)
    dirs = ensure_job_dirs(job_id)
    final_topics = dirs["step2"] / "final_topics.json"
    write_topics_json(normalized, final_topics)
    upsert_job_files(job_id, final_topics_path=str(final_topics))
    update_job(job_id, status=JOB_STATUS_STEP2_CONFIRMED, progress=PROGRESS_STEP2_CONFIRMED)
    return normalized


def get_step2(job_id: str) -> list[dict[str, Any]]:
    return list_step2_chapters(job_id)
