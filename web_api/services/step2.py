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


def _kept_lines(job_id: str) -> list[dict[str, Any]]:
    lines = list_step1_lines(job_id)
    kept = [item for item in lines if not bool(item.get("user_final_remove", False))]
    kept.sort(key=lambda item: int(item["line_id"]))
    return kept


def _parse_block_range(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        normalized = int(value)
        if normalized < 1:
            return None
        return normalized, normalized
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if "-" not in raw:
        try:
            normalized = int(raw)
        except ValueError:
            return None
        if normalized < 1:
            return None
        return normalized, normalized

    start_raw, end_raw = raw.split("-", 1)
    try:
        start_id = int(start_raw.strip())
        end_id = int(end_raw.strip())
    except ValueError:
        return None
    if start_id < 1 or end_id < start_id:
        return None
    return start_id, end_id


def _format_block_range(start_id: int, end_id: int) -> str:
    return str(start_id) if start_id == end_id else f"{start_id}-{end_id}"


def _line_ids_to_block_range(line_ids: list[int], kept_lines: list[dict[str, Any]]) -> str:
    if not line_ids or not kept_lines:
        return ""
    position_by_line_id = {
        int(item["line_id"]): index + 1 for index, item in enumerate(kept_lines)
    }
    positions = sorted(
        {
            position_by_line_id[int(line_id)]
            for line_id in line_ids
            if int(line_id) in position_by_line_id
        }
    )
    if not positions:
        return ""
    return _format_block_range(positions[0], positions[-1])


def _topic_block_range(topic: dict[str, Any], kept_lines: list[dict[str, Any]]) -> str:
    for key in ("block_range", "segment_range", "line_range", "range"):
        parsed = _parse_block_range(topic.get(key))
        if parsed is not None:
            return _format_block_range(*parsed)

    start_raw = topic.get("start_segment_id", topic.get("start_line_id"))
    end_raw = topic.get("end_segment_id", topic.get("end_line_id"))
    if isinstance(start_raw, (int, float)) and isinstance(end_raw, (int, float)):
        start_id = int(start_raw)
        end_id = int(end_raw)
        if start_id >= 1 and end_id >= start_id:
            return _format_block_range(start_id, end_id)

    line_ids_raw = topic.get("line_ids")
    if isinstance(line_ids_raw, list):
        line_ids = [int(item) for item in line_ids_raw if isinstance(item, (int, float))]
        return _line_ids_to_block_range(line_ids, kept_lines)

    segment_ids_raw = topic.get("segment_ids")
    if isinstance(segment_ids_raw, list):
        segment_ids = [int(item) for item in segment_ids_raw if isinstance(item, (int, float))]
        if segment_ids:
            return _format_block_range(segment_ids[0], segment_ids[-1])

    return ""


def _ensure_full_block_coverage(chapters: list[dict[str, Any]], total_blocks: int) -> None:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")
    if total_blocks < 1:
        raise RuntimeError("kept step1 lines missing for step2")

    cursor = 1
    for idx, chapter in enumerate(chapters, start=1):
        parsed = _parse_block_range(chapter.get("block_range"))
        if parsed is None:
            raise RuntimeError(f"chapter block_range invalid: {idx}")
        start_id, end_id = parsed
        if start_id != cursor:
            raise RuntimeError(f"chapter block_range not contiguous: {idx}")
        chapter["block_range"] = _format_block_range(start_id, end_id)
        cursor = end_id + 1

    if cursor - 1 != total_blocks:
        raise RuntimeError("chapter block_range does not fully cover kept subtitles")


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
    update_job(
        job_id,
        status=JOB_STATUS_STEP2_RUNNING,
        progress=PROGRESS_STEP2_RUNNING + 1,
        stage_code="GENERATING_CHAPTERS",
        stage_message="正在生成章节结构...",
    )
    push(PROGRESS_STEP2_RUNNING + 1)
    run_topic_segmentation_from_optimized_srt(
        optimized_srt_path=source_srt,
        cut_srt_output_path=cut_srt,
        topics_output_path=generated_topics,
        options=options,
    )
    update_job(
        job_id,
        status=JOB_STATUS_STEP2_RUNNING,
        progress=PROGRESS_STEP2_RUNNING + 8,
        stage_code="FINALIZING_CHAPTERS",
        stage_message="正在整理章节结果...",
    )
    push(PROGRESS_STEP2_RUNNING + 8)

    kept_lines = _kept_lines(job_id)
    chapters = _load_chapters(generated_topics, kept_lines=kept_lines)
    if not chapters:
        raise RuntimeError("step2 generated empty chapter list")
    _ensure_full_block_coverage(chapters, total_blocks=len(kept_lines))
    replace_step2_chapters(job_id, chapters)
    upsert_job_files(
        job_id,
        topics_path=str(generated_topics),
        final_topics_path=str(dirs["step2"] / "final_topics.json"),
    )
    update_job(
        job_id,
        status=JOB_STATUS_STEP2_READY,
        progress=PROGRESS_STEP2_READY,
        stage_code="CHAPTERS_READY",
        stage_message="章节已生成，请确认章节标题和边界。",
    )


def _load_chapters(path: Path, *, kept_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        block_range = _topic_block_range(topic, kept_lines)
        if not block_range:
            continue

        title = str(topic.get("title") or "").strip() or f"章节{idx}"
        chapters.append(
            {
                "chapter_id": idx,
                "title": title,
                "start": start,
                "end": end,
                "block_range": block_range,
            }
        )
    return chapters


def confirm_step2(job_id: str, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")
    kept_lines = _kept_lines(job_id)
    if not kept_lines:
        raise RuntimeError("kept step1 lines missing for step2")

    normalized: list[dict[str, Any]] = []
    for idx, chapter in enumerate(chapters, start=1):
        parsed = _parse_block_range(chapter.get("block_range"))
        if parsed is None:
            raise RuntimeError(f"chapter block_range invalid: {idx}")
        start_idx, end_idx = parsed
        if end_idx > len(kept_lines):
            raise RuntimeError(f"chapter block_range out of bounds: {idx}")
        chosen = kept_lines[start_idx - 1 : end_idx]
        if not chosen:
            raise RuntimeError(f"chapter block_range empty: {idx}")
        title = str(chapter.get("title", "")).strip() or f"章节{idx}"
        normalized.append(
            {
                "chapter_id": int(chapter.get("chapter_id", idx)),
                "title": title,
                "start": float(chosen[0]["start"]),
                "end": float(chosen[-1]["end"]),
                "block_range": _format_block_range(start_idx, end_idx),
            }
        )
    _ensure_full_block_coverage(normalized, total_blocks=len(kept_lines))
    replace_step2_chapters(job_id, normalized)
    dirs = ensure_job_dirs(job_id)
    final_topics = dirs["step2"] / "final_topics.json"
    write_topics_json(normalized, final_topics)
    upsert_job_files(job_id, final_topics_path=str(final_topics))
    update_job(
        job_id,
        status=JOB_STATUS_STEP2_CONFIRMED,
        progress=PROGRESS_STEP2_CONFIRMED,
        stage_code="EXPORT_READY",
        stage_message="章节已确认，正在准备导出...",
    )
    return normalized


def get_step2(job_id: str) -> list[dict[str, Any]]:
    rows = list_step2_chapters(job_id)
    kept_lines = _kept_lines(job_id)
    normalized: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        block_range = _topic_block_range(row, kept_lines)
        if not block_range:
            continue
        parsed = _parse_block_range(block_range)
        if parsed is None:
            continue
        start_idx, end_idx = parsed
        if end_idx > len(kept_lines):
            continue
        start = float(row.get("start", kept_lines[start_idx - 1]["start"]))
        end = float(row.get("end", kept_lines[end_idx - 1]["end"]))
        normalized.append(
            {
                "chapter_id": int(row.get("chapter_id", idx)),
                "title": str(row.get("title") or f"章节{idx}"),
                "start": start,
                "end": end,
                "block_range": block_range,
            }
        )
    return normalized
