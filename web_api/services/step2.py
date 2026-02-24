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
    JOB_STATUS_STEP2_RUNNING,
    PROGRESS_STEP2_CONFIRMED,
    PROGRESS_STEP2_READY,
    PROGRESS_STEP2_RUNNING,
)
from ..repository import (
    get_job_files,
    list_step1_lines,
    list_step2_chapters,
    replace_step2_chapters,
    update_job,
    upsert_job_files,
)
from .pipeline_options import build_pipeline_options
from ..utils.srt_utils import write_topics_json


def _kept_line_ids(job_id: str) -> list[int]:
    lines = list_step1_lines(job_id)
    kept = [int(item["line_id"]) for item in lines if not bool(item.get("user_final_remove", False))]
    kept.sort()
    return kept


def _map_line_ids_to_step1(raw_line_ids: list[int], kept_line_ids: list[int]) -> list[int]:
    if not raw_line_ids:
        return []
    kept_set = set(kept_line_ids)
    mapped: list[int] = []
    seen: set[int] = set()
    total = len(kept_line_ids)
    for raw in raw_line_ids:
        candidate: int | None = None
        if raw in kept_set:
            candidate = raw
        elif 1 <= raw <= total:
            # Fallback: if topic ids are cut.srt sequential indexes, map by kept order.
            candidate = kept_line_ids[raw - 1]
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        mapped.append(candidate)
    return mapped


def _ensure_full_line_coverage(chapters: list[dict[str, Any]], kept_line_ids: list[int]) -> None:
    if not chapters:
        return

    kept_set = set(kept_line_ids)
    for chapter in chapters:
        raw = chapter.get("line_ids") or []
        ids = [int(item) for item in raw if isinstance(item, (int, float))]
        mapped = _map_line_ids_to_step1(ids, kept_line_ids)
        chapter["line_ids"] = mapped

    assigned = {lid for chapter in chapters for lid in chapter.get("line_ids", []) if lid in kept_set}
    missing = [lid for lid in kept_line_ids if lid not in assigned]
    if not missing:
        return

    for lid in missing:
        target_idx = len(chapters) - 1
        for idx, chapter in enumerate(chapters):
            ids = chapter.get("line_ids") or []
            if ids and lid <= max(ids):
                target_idx = idx
                break
        chapters[target_idx]["line_ids"].append(lid)

    for chapter in chapters:
        deduped = sorted(set(int(item) for item in chapter.get("line_ids", []) if int(item) in kept_set))
        chapter["line_ids"] = deduped


def run_step2(job_id: str) -> None:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files missing for step2")
    if not files.get("final_step1_srt_path"):
        raise RuntimeError("final_step1.srt missing for step2")
    last_progress = PROGRESS_STEP2_RUNNING

    def push(progress: int) -> None:
        nonlocal last_progress
        value = max(last_progress, min(int(progress), PROGRESS_STEP2_READY - 1))
        if value <= last_progress:
            return
        update_job(job_id, status=JOB_STATUS_STEP2_RUNNING, progress=value)
        last_progress = value

    dirs = ensure_job_dirs(job_id)
    source_srt = Path(files["final_step1_srt_path"])
    cut_srt = dirs["step2"] / "cut.srt"
    options = build_pipeline_options()
    generated_topics = dirs["step2"] / "topics.json"
    push(PROGRESS_STEP2_RUNNING + 1)
    run_topic_segmentation_from_optimized_srt(
        optimized_srt_path=source_srt,
        cut_srt_output_path=cut_srt,
        topics_output_path=generated_topics,
        options=options,
    )
    push(PROGRESS_STEP2_RUNNING + 8)

    kept_line_ids = _kept_line_ids(job_id)
    chapters = _load_chapters(generated_topics)
    if not chapters:
        raise RuntimeError("step2 generated empty chapter list")
    _ensure_full_line_coverage(chapters, kept_line_ids)
    push(PROGRESS_STEP2_READY - 1)

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

        title = str(topic.get("title") or "").strip() or f"章节{idx}"
        raw_summary = str(topic.get("summary") or title or "").strip()
        summary = title if (not raw_summary or raw_summary == title) else raw_summary

        chapters.append(
            {
                "chapter_id": idx,
                "title": title,
                "summary": summary,
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
        title = str(chapter.get("title", "")).strip() or f"章节{idx}"
        raw_summary = str(chapter.get("summary", "")).strip()
        summary = title if (not raw_summary or raw_summary == title) else raw_summary
        normalized.append(
            {
                "chapter_id": int(chapter.get("chapter_id", idx)),
                "title": title,
                "summary": summary,
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
