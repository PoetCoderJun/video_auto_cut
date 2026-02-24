from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt

from ..config import ensure_job_dirs, get_settings
from ..constants import DEFAULT_ENCODING
from ..repository import get_job_files, list_step2_chapters
from ..utils.media import probe_video_stream


def resolve_render_source_path(job_id: str) -> Path:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    video_path = files.get("video_path")
    if not video_path:
        raise RuntimeError("render source video missing")

    path = Path(video_path)
    if not path.exists():
        raise RuntimeError("render source video missing")
    return path


def build_web_render_config(job_id: str, *, source_url: str) -> dict[str, Any]:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    video_path = files.get("video_path")
    step1_srt_path = files.get("final_step1_srt_path")
    if not video_path or not step1_srt_path:
        raise RuntimeError("render inputs missing")

    source_path = Path(video_path)
    if not source_path.exists():
        raise RuntimeError("render source video missing")

    settings = get_settings()
    dirs = ensure_job_dirs(job_id)
    cut_srt_path = dirs["render"] / "web.cut.srt"
    cut_timeline = build_cut_srt_from_optimized_srt(
        source_srt_path=str(step1_srt_path),
        output_srt_path=str(cut_srt_path),
        encoding=DEFAULT_ENCODING,
        merge_gap_s=float(settings.cut_merge_gap),
    )

    captions = [_normalize_caption(item) for item in list(cut_timeline["captions"])]
    captions = [item for item in captions if item is not None]
    if not captions:
        raise RuntimeError("render captions missing")

    segments = [_normalize_segment(item) for item in list(cut_timeline["segments"])]
    segments = [item for item in segments if item is not None]
    if not segments:
        raise RuntimeError("render segments missing")

    topics = [_normalize_topic(item) for item in list_step2_chapters(job_id)]
    topics = [item for item in topics if item is not None]
    topics.sort(key=lambda item: float(item["start"]))

    media_info = probe_video_stream(source_path)
    fps = _resolve_fps(media_info)
    width, height = _resolve_dimensions(media_info)
    duration_s = sum(float(item["end"]) - float(item["start"]) for item in segments)
    if duration_s <= 0:
        duration_s = float(media_info.get("duration_sec") or captions[-1]["end"])
    duration_in_frames = max(1, int(math.ceil(duration_s * fps)))

    output_name = f"{source_path.stem}_remotion.mp4"
    input_props: dict[str, Any] = {
        "src": source_url,
        "captions": captions,
        "segments": segments,
        "topics": topics,
        "fps": fps,
        "width": width,
        "height": height,
    }

    return {
        "source_url": source_url,
        "output_name": output_name,
        "composition": {
            "id": "StitchVideoWeb",
            "fps": fps,
            "width": width,
            "height": height,
            "durationInFrames": duration_in_frames,
        },
        "input_props": input_props,
    }


def _normalize_caption(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        start = float(raw.get("start"))
        end = float(raw.get("end"))
    except (TypeError, ValueError):
        return None

    if end <= start:
        return None

    text = str(raw.get("text") or "").strip()
    if not text:
        return None

    index_raw = raw.get("index")
    try:
        index = int(index_raw)
    except (TypeError, ValueError):
        index = 0

    return {
        "index": index,
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
    }


def _normalize_segment(raw: dict[str, Any]) -> dict[str, float] | None:
    try:
        start = float(raw.get("start"))
        end = float(raw.get("end"))
    except (TypeError, ValueError):
        return None

    if end <= start:
        return None

    return {
        "start": round(start, 3),
        "end": round(end, 3),
    }


def _normalize_topic(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        start = float(raw.get("start"))
        end = float(raw.get("end"))
    except (TypeError, ValueError):
        return None

    if end <= start:
        return None

    title = str(raw.get("title") or "").strip() or "章节"
    summary = str(raw.get("summary") or "").strip()

    return {
        "title": title,
        "summary": summary,
        "start": round(start, 3),
        "end": round(end, 3),
    }


def _resolve_fps(media_info: dict[str, str | float | int | None]) -> float:
    value = media_info.get("fps")
    try:
        fps = float(value) if value is not None else 30.0
    except (TypeError, ValueError):
        fps = 30.0
    if not math.isfinite(fps) or fps <= 0:
        fps = 30.0
    return min(30.0, fps)


def _resolve_dimensions(media_info: dict[str, str | float | int | None]) -> tuple[int, int]:
    width_raw = media_info.get("width")
    height_raw = media_info.get("height")
    try:
        width = int(width_raw) if width_raw is not None else 1920
        height = int(height_raw) if height_raw is not None else 1080
    except (TypeError, ValueError):
        return 1920, 1080

    if width <= 0 or height <= 0:
        return 1920, 1080

    max_height = 1080
    if height > max_height:
        scale = max_height / float(height)
        width = int(round(width * scale))
        height = max_height

    return _ensure_even(width), _ensure_even(height)


def _ensure_even(value: int) -> int:
    if value <= 2:
        return 2
    if value % 2 == 0:
        return value
    return value - 1
