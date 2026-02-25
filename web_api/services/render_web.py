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


def build_web_render_config(
    job_id: str,
    *,
    source_url: str,
    fps: float | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    step1_srt_path = files.get("final_step1_srt_path")
    if not step1_srt_path:
        raise RuntimeError("render inputs missing")

    source_path: Path | None = None
    video_path = files.get("video_path")
    if isinstance(video_path, str) and video_path.strip():
        candidate = Path(video_path)
        if candidate.exists():
            source_path = candidate

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

    media_info: dict[str, str | float | int | None] = {}
    if source_path is not None and (fps is None or width is None or height is None or duration_sec is None):
        media_info = probe_video_stream(source_path)

    resolved_fps = _resolve_fps(fps, media_info)
    resolved_width, resolved_height = _resolve_dimensions(width, height, media_info)
    segment_duration_in_frames = _duration_frames_from_segments(segments, resolved_fps)
    if segment_duration_in_frames > 0:
        # Keep composition length strictly aligned with stitched segment frames.
        duration_in_frames = segment_duration_in_frames
    else:
        resolved_duration_s = _resolve_duration(duration_sec, media_info, captions, segments)
        duration_in_frames = max(1, int(math.ceil(resolved_duration_s * resolved_fps)))

    output_stem = source_path.stem if source_path is not None else job_id
    output_name = f"{output_stem}_remotion.mp4"
    input_props: dict[str, Any] = {
        "src": source_url,
        "captions": captions,
        "segments": segments,
        "topics": topics,
        "fps": resolved_fps,
        "width": resolved_width,
        "height": resolved_height,
    }

    return {
        "source_url": source_url,
        "output_name": output_name,
        "has_server_source": source_path is not None,
        "composition": {
            "id": "StitchVideoWeb",
            "fps": resolved_fps,
            "width": resolved_width,
            "height": resolved_height,
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


def _resolve_fps(override: float | None, media_info: dict[str, str | float | int | None]) -> float:
    value = override if override is not None else media_info.get("fps")
    try:
        fps = float(value) if value is not None else 30.0
    except (TypeError, ValueError):
        fps = 30.0
    if not math.isfinite(fps) or fps <= 0:
        fps = 30.0
    # Keep reasonable bounds; allow >30fps for accurate trimming.
    return max(1.0, min(120.0, fps))


def _resolve_dimensions(
    override_width: int | None,
    override_height: int | None,
    media_info: dict[str, str | float | int | None],
) -> tuple[int, int]:
    width_raw = override_width if override_width is not None else media_info.get("width")
    height_raw = override_height if override_height is not None else media_info.get("height")
    try:
        width = int(width_raw) if width_raw is not None else 1920
        height = int(height_raw) if height_raw is not None else 1080
    except (TypeError, ValueError):
        return 1920, 1080

    if width <= 0 or height <= 0:
        return 1920, 1080

    # Keep original upload resolution (no forced 1080p downscale),
    # so subtitle edges stay sharp in browser-side render output.
    return _ensure_even(width), _ensure_even(height)

def _resolve_duration(
    override: float | None,
    media_info: dict[str, str | float | int | None],
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> float:
    duration_s = float(override) if override is not None else 0.0
    if not math.isfinite(duration_s) or duration_s <= 0:
        duration_s = 0.0

    if duration_s <= 0:
        try:
            duration_s = float(media_info.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            duration_s = 0.0

    if duration_s <= 0:
        try:
            duration_s = sum(float(item["end"]) - float(item["start"]) for item in segments)
        except Exception:
            duration_s = 0.0

    if duration_s <= 0:
        try:
            duration_s = float(captions[-1]["end"])
        except Exception:
            duration_s = 1.0

    if not math.isfinite(duration_s) or duration_s <= 0:
        return 1.0
    return duration_s


def _duration_frames_from_segments(segments: list[dict[str, Any]], fps: float) -> int:
    total = 0
    for item in sorted(segments, key=lambda seg: float(seg["start"])):
        start = float(item["start"])
        end = float(item["end"])
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        trim_before = max(0, int(math.floor(start * fps)))
        trim_after = max(trim_before + 1, int(math.ceil(end * fps)))
        total += max(1, trim_after - trim_before)
    return max(0, total)


def _ensure_even(value: int) -> int:
    if value <= 2:
        return 2
    if value % 2 == 0:
        return value
    return value - 1
