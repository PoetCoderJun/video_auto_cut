from __future__ import annotations

import math
from typing import Any

_MISSING_DIMENSIONS_MESSAGE = "缺少视频分辨率，请重新选择源文件后重试"
_INVALID_DIMENSIONS_MESSAGE = "视频分辨率无效，请重新选择源文件后重试"


def _build_cut_timeline(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    cursor = 0.0
    timeline: list[dict[str, float]] = []
    for item in sorted(segments, key=lambda seg: float(seg["start"])):
        start = float(item["start"])
        end = float(item["end"])
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        duration = end - start
        timeline.append(
            {
                "start": start,
                "end": end,
                "out_start": cursor,
                "out_end": cursor + duration,
            }
        )
        cursor += duration
    return timeline


def _map_original_time_to_cut_time(
    time_sec: float,
    timeline: list[dict[str, float]],
    *,
    prefer_end: bool,
) -> float:
    if not timeline:
        return max(0.0, float(time_sec))

    eps = 1e-4
    for index, segment in enumerate(timeline):
        start = float(segment["start"])
        end = float(segment["end"])
        out_start = float(segment["out_start"])
        out_end = float(segment["out_end"])

        if time_sec < start - eps:
            if prefer_end and index > 0:
                return float(timeline[index - 1]["out_end"])
            return out_start

        if time_sec <= end + eps:
            clamped = min(max(time_sec, start), end)
            return out_start + (clamped - start)

    return float(timeline[-1]["out_end"])


def remap_topics_to_cut_timeline(
    topics: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline = _build_cut_timeline(segments)
    if not timeline:
        return topics

    remapped: list[dict[str, Any]] = []
    for topic in topics:
        start = float(topic["start"])
        end = float(topic["end"])
        cut_start = _map_original_time_to_cut_time(start, timeline, prefer_end=False)
        cut_end = _map_original_time_to_cut_time(end, timeline, prefer_end=True)
        if cut_end <= cut_start:
            continue
        remapped.append(
            {
                **topic,
                "start": round(cut_start, 3),
                "end": round(cut_end, 3),
            }
        )
    return remapped


def ensure_even(value: int) -> int:
    if value <= 2:
        return 2
    if value % 2 == 0:
        return value
    return value - 1


def resolve_dimensions(
    override_width: int | None,
    override_height: int | None,
) -> tuple[int, int]:
    if override_width is None or override_height is None:
        raise ValueError(_MISSING_DIMENSIONS_MESSAGE)
    try:
        width = int(override_width)
        height = int(override_height)
    except (TypeError, ValueError) as exc:
        raise ValueError(_INVALID_DIMENSIONS_MESSAGE) from exc

    if width <= 0 or height <= 0:
        raise ValueError(_INVALID_DIMENSIONS_MESSAGE)

    return ensure_even(width), ensure_even(height)
