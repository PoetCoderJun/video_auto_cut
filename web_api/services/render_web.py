from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt

from ..config import ensure_job_dirs, get_settings
from ..constants import DEFAULT_ENCODING
from ..job_file_repository import get_job_files, list_final_test_chapters
from .render_caption_labels import attach_llm_labels_to_captions
from .render_word_timing import attach_remapped_tokens_to_captions
from .render_typography import (
    remap_topics_to_cut_timeline,
    resolve_dimensions as _resolve_dimensions,
)


def build_web_render_config(
    job_id: str,
    *,
    fps: float | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    contract_config = _build_web_render_config_from_subtitle_render_v1_source(
        files,
        fps=fps,
        width=width,
        height=height,
        duration_sec=duration_sec,
    )
    if contract_config is not None:
        return contract_config

    test_srt_path = files.get("final_test_srt_path")
    if not test_srt_path:
        raise RuntimeError("render inputs missing")

    settings = get_settings()
    dirs = ensure_job_dirs(job_id)
    cut_srt_path = dirs["render"] / "web.cut.srt"
    cut_timeline = build_cut_srt_from_optimized_srt(
        source_srt_path=str(test_srt_path),
        output_srt_path=str(cut_srt_path),
        encoding=DEFAULT_ENCODING,
        merge_gap_s=float(settings.cut_merge_gap),
    )

    captions = [_normalize_caption(item) for item in list(cut_timeline["captions"])]
    captions = [item for item in captions if item is not None]
    if not captions:
        raise RuntimeError("render captions missing")
    captions = attach_remapped_tokens_to_captions(
        captions=captions,
        kept_subtitles=list(cut_timeline.get("kept_subtitles") or []),
        segments=list(cut_timeline.get("segments") or []),
        sidecar_path=_resolve_asr_words_sidecar_path(files),
    )
    captions = attach_llm_labels_to_captions(captions=captions, job_id=job_id)

    segments = [_normalize_segment(item) for item in list(cut_timeline["segments"])]
    segments = [item for item in segments if item is not None]
    if not segments:
        raise RuntimeError("render segments missing")

    topics = [_normalize_topic(item) for item in list_final_test_chapters(job_id)]
    topics = [item for item in topics if item is not None]
    topics = remap_topics_to_cut_timeline(topics, segments)
    topics.sort(key=lambda item: float(item["start"]))

    resolved_fps = _resolve_fps(fps)
    resolved_width, resolved_height = _resolve_dimensions(width, height)
    segment_duration_in_frames = _duration_frames_from_segments(segments, resolved_fps)
    if segment_duration_in_frames > 0:
        duration_in_frames = segment_duration_in_frames
    else:
        resolved_duration_s = _resolve_duration(duration_sec, captions, segments)
        duration_in_frames = max(1, int(math.ceil(resolved_duration_s * resolved_fps)))

    output_name = f"{job_id}_export.mp4"
    input_props: dict[str, Any] = {
        "src": "",
        "captions": captions,
        "segments": segments,
        "topics": topics,
        "fps": resolved_fps,
        "width": resolved_width,
        "height": resolved_height,
    }

    return {
        "output_name": output_name,
        "composition": {
            "id": "StitchVideoWeb",
            "fps": resolved_fps,
            "width": resolved_width,
            "height": resolved_height,
            "durationInFrames": duration_in_frames,
        },
        "input_props": input_props,
    }


def _build_web_render_config_from_subtitle_render_v1_source(
    files: dict[str, Any],
    *,
    fps: float | None,
    width: int | None,
    height: int | None,
    duration_sec: float | None,
) -> dict[str, Any] | None:
    contract = _load_subtitle_render_v1_contract(files)
    if contract is None:
        return None
    return _subtitle_render_v1_to_web_render_config(
        contract,
        fps=fps,
        width=width,
        height=height,
        duration_sec=duration_sec,
    )


def _load_subtitle_render_v1_contract(files: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("subtitle_render_v1", "subtitle_render", "render_json"):
        candidate = files.get(key)
        if isinstance(candidate, dict) and _is_subtitle_render_v1_contract(candidate):
            return candidate

    for key in (
        "subtitle_render_v1_path",
        "subtitle_render_path",
        "render_json_path",
        "render_contract_path",
    ):
        candidate = files.get(key)
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        path = Path(candidate)
        if not path.exists() or not path.is_file():
            continue
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict) and _is_subtitle_render_v1_contract(parsed):
            return parsed

    return None


def _is_subtitle_render_v1_contract(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    marker = str(
        value.get("contract")
        or value.get("version")
        or value.get("type")
        or ""
    ).strip()
    return marker == "subtitle-render.v1"


def _subtitle_render_v1_to_web_render_config(
    contract: dict[str, Any],
    *,
    fps: float | None,
    width: int | None,
    height: int | None,
    duration_sec: float | None,
) -> dict[str, Any]:
    payload = _subtitle_render_v1_payload(contract)
    composition = payload.get("composition") if isinstance(payload.get("composition"), dict) else {}
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}

    captions = [_normalize_caption(item) for item in list(payload.get("captions") or [])]
    captions = [item for item in captions if item is not None]
    if not captions:
        raise RuntimeError("subtitle-render.v1 captions missing")

    segments = [_normalize_segment(item) for item in list(payload.get("segments") or [])]
    segments = [item for item in segments if item is not None]
    if not segments:
        raise RuntimeError("subtitle-render.v1 segments missing")

    raw_topics = payload.get("topics") or payload.get("chapters") or []
    topics = [_normalize_topic(item) for item in list(raw_topics)]
    topics = [item for item in topics if item is not None]
    topics.sort(key=lambda item: float(item["start"]))

    resolved_fps = _resolve_fps(fps if fps is not None else composition.get("fps") or video.get("fps") or payload.get("fps"))
    resolved_width, resolved_height = _resolve_dimensions(
        width if width is not None else composition.get("width") or video.get("width") or payload.get("width"),
        height if height is not None else composition.get("height") or video.get("height") or payload.get("height"),
    )

    duration_in_frames_raw = composition.get("durationInFrames")
    try:
        duration_in_frames = int(duration_in_frames_raw)
    except (TypeError, ValueError):
        duration_in_frames = 0

    if duration_in_frames <= 0:
        segment_duration_in_frames = _duration_frames_from_segments(segments, resolved_fps)
        if segment_duration_in_frames > 0:
            duration_in_frames = segment_duration_in_frames
        else:
            resolved_duration_s = _resolve_duration(duration_sec, captions, segments)
            duration_in_frames = max(1, int(math.ceil(resolved_duration_s * resolved_fps)))

    input_props: dict[str, Any] = {
        "src": str(payload.get("src") or video.get("src") or ""),
        "captions": captions,
        "segments": segments,
        "topics": topics,
        "fps": resolved_fps,
        "width": resolved_width,
        "height": resolved_height,
    }
    for key in (
        "subtitleTheme",
        "subtitleScale",
        "subtitleYPercent",
        "progressScale",
        "progressYPercent",
        "chapterScale",
        "showSubtitles",
        "showProgress",
        "showChapter",
        "progressLabelMode",
    ):
        value = payload.get(key)
        if value is not None:
            input_props[key] = value

    output_name = str(contract.get("output_name") or contract.get("outputName") or "subtitle-render_export.mp4")
    if not output_name.strip():
        output_name = "subtitle-render_export.mp4"

    return {
        "output_name": output_name,
        "composition": {
            "id": "StitchVideoWeb",
            "fps": resolved_fps,
            "width": resolved_width,
            "height": resolved_height,
            "durationInFrames": max(1, duration_in_frames),
        },
        "input_props": input_props,
    }


def _subtitle_render_v1_payload(contract: dict[str, Any]) -> dict[str, Any]:
    for key in ("render", "input_props", "props", "payload"):
        candidate = contract.get(key)
        if isinstance(candidate, dict):
            if key == "render":
                nested = candidate.get("input_props") if isinstance(candidate.get("input_props"), dict) else candidate
                return nested
            return candidate
    return contract


def _resolve_asr_words_sidecar_path(files: dict[str, Any]) -> str | None:
    raw_sidecar = files.get("asr_words_sidecar_path")
    if isinstance(raw_sidecar, str) and raw_sidecar.strip():
        return raw_sidecar
    raw_srt = files.get("srt_path")
    if isinstance(raw_srt, str) and raw_srt.strip():
        from video_auto_cut.asr.word_timing_sidecar import sidecar_path_for_srt

        candidate = sidecar_path_for_srt(raw_srt)
        if candidate.exists():
            return str(candidate)
    return None


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

    normalized: dict[str, Any] = {
        "index": index,
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
    }

    tokens = [_normalize_caption_token(item) for item in list(raw.get("tokens") or [])]
    tokens = [item for item in tokens if item is not None]
    if tokens:
        normalized["tokens"] = tokens

    label = _normalize_caption_label(raw.get("label"))
    if label is not None:
        normalized["label"] = label

    alignment_mode = str(raw.get("alignmentMode") or "").strip()
    if alignment_mode in {"exact", "fuzzy", "degraded", "missing"}:
        normalized["alignmentMode"] = alignment_mode

    return normalized


def _normalize_caption_token(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    try:
        start = float(raw.get("start"))
        end = float(raw.get("end"))
    except (TypeError, ValueError):
        return None
    if end < start:
        return None
    normalized: dict[str, Any] = {
        "text": text,
        "start": round(start, 3),
        "end": round(end, 3),
    }
    source_word_index = raw.get("sourceWordIndex")
    try:
        normalized_source_word_index = int(source_word_index)
    except (TypeError, ValueError):
        normalized_source_word_index = None
    if normalized_source_word_index is not None:
        normalized["sourceWordIndex"] = normalized_source_word_index
    return normalized


def _normalize_caption_label(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    normalized: dict[str, Any] = {}
    badge_text = str(raw.get("badgeText") or "").strip()
    if badge_text:
        normalized["badgeText"] = badge_text
    emphasis_spans = [_normalize_caption_emphasis_span(item) for item in list(raw.get("emphasisSpans") or [])]
    emphasis_spans = [item for item in emphasis_spans if item is not None]
    if emphasis_spans:
        normalized["emphasisSpans"] = emphasis_spans
    return normalized or None


def _normalize_caption_emphasis_span(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    try:
        start_token = int(raw.get("startToken"))
        end_token = int(raw.get("endToken"))
    except (TypeError, ValueError):
        return None
    if end_token <= start_token:
        return None
    return {
        "startToken": start_token,
        "endToken": end_token,
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
    return {
        "title": title,
        "start": round(start, 3),
        "end": round(end, 3),
    }


def _resolve_fps(override: float | None) -> float:
    try:
        fps = float(override) if override is not None else 30.0
    except (TypeError, ValueError):
        fps = 30.0
    if not math.isfinite(fps) or fps <= 0:
        fps = 30.0
    return max(1.0, min(120.0, fps))


def _resolve_duration(
    override: float | None,
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> float:
    duration_s = float(override) if override is not None else 0.0
    if not math.isfinite(duration_s) or duration_s <= 0:
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
