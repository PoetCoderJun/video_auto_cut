from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt
from video_auto_cut.rendering.subtitle_render_contract import (
    build_subtitle_render_v1_contract,
    build_subtitle_style_llm_config,
    normalize_subtitle_theme as normalize_render_contract_theme,
    write_subtitle_render_v1_contract,
)

from ..config import ensure_job_dirs, get_settings
from ..constants import DEFAULT_ENCODING
from ..job_file_repository import get_job_files, list_final_test_chapters, upsert_job_files
from .render_word_timing import attach_remapped_tokens_to_captions
from .render_typography import (
    remap_topics_to_cut_timeline,
    resolve_dimensions as _resolve_dimensions,
)

_TIMECODE_RE = re.compile(r"^(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})\.(?P<ms>\d{3})$")


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

    segments = [_normalize_segment(item) for item in list(cut_timeline["segments"])]
    segments = [item for item in segments if item is not None]
    if not segments:
        raise RuntimeError("render segments missing")

    topics = [_normalize_topic(item) for item in list_final_test_chapters(job_id)]
    topics = [item for item in topics if item is not None]
    topics = remap_topics_to_cut_timeline(topics, segments)
    topics.sort(key=lambda item: float(item["start"]))

    generated_contract = build_subtitle_render_v1_contract(
        captions=captions,
        segments=segments,
        topics=topics,
        output_name=f"{job_id}_export.mp4",
        subtitle_theme=normalize_render_contract_theme(files.get("subtitle_theme") or "white"),
        llm_config=_build_subtitle_style_llm_config(),
    )
    contract_path = dirs["render"] / "subtitle-render.v1.json"
    write_subtitle_render_v1_contract(generated_contract, contract_path)
    upsert_job_files(job_id, subtitle_render_v1_path=str(contract_path))
    return _subtitle_render_v1_to_web_render_config(
        generated_contract,
        fps=fps,
        width=width,
        height=height,
        duration_sec=duration_sec,
    )


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
        segments = [
            {"start": float(item["start"]), "end": float(item["end"])}
            for item in captions
        ]

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
    subtitle_theme = _normalize_subtitle_theme(payload.get("subtitleTheme"))
    if subtitle_theme is not None:
        input_props["subtitleTheme"] = subtitle_theme

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


def _build_subtitle_style_llm_config() -> dict[str, Any]:
    settings = get_settings()
    return build_subtitle_style_llm_config(
        base_url=getattr(settings, "llm_base_url", None),
        model=getattr(settings, "llm_model", None),
        api_key=getattr(settings, "llm_api_key", None),
        timeout=int(getattr(settings, "llm_timeout", 60)),
        max_tokens=getattr(settings, "llm_max_tokens", None),
    )


def _normalize_caption(raw: dict[str, Any]) -> dict[str, Any] | None:
    start = _parse_time_value(raw.get("start"))
    end = _parse_time_value(raw.get("end"))
    if start is None or end is None:
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
    label_raw = raw.get("label")
    token_meta = _tokenize_caption_text(text, start, end)
    if not tokens and isinstance(label_raw, dict) and list(label_raw.get("highlights") or []):
        tokens = [
            {
                "text": item["text"],
                "start": item["start"],
                "end": item["end"],
            }
            for item in token_meta
        ]
    if tokens:
        normalized["tokens"] = tokens

    normalized_token_meta = _build_token_meta_from_tokens(tokens) if tokens else token_meta
    label = _normalize_caption_label(label_raw, normalized_token_meta)
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
    start = _parse_time_value(raw.get("start"))
    end = _parse_time_value(raw.get("end"))
    if start is None or end is None:
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


def _normalize_caption_label(raw: Any, token_meta: list[dict[str, Any]]) -> dict[str, Any] | None:
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
    highlights = _normalize_caption_highlights(raw.get("highlights"), token_meta)
    if highlights:
        normalized["highlights"] = highlights
    return normalized or None


def _normalize_caption_highlights(raw: Any, token_meta: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    used_char_starts: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        try:
            start_token = int(item.get("startToken"))
            end_token = int(item.get("endToken"))
            if end_token <= start_token:
                raise ValueError
            resolved = {"startToken": start_token, "endToken": end_token}
        except (TypeError, ValueError):
            resolved = _find_highlight_token_range(token_meta, text, used_char_starts) if text else None
        if resolved is None:
            continue
        entry: dict[str, Any] = {
            **resolved,
        }
        if text:
            entry["text"] = text
        color = str(item.get("color") or "").strip()
        if color:
            entry["color"] = color
        try:
            font_scale = float(item.get("fontScale"))
        except (TypeError, ValueError):
            font_scale = None
        if font_scale is not None and math.isfinite(font_scale) and font_scale > 0:
            entry["fontScale"] = font_scale
        normalized.append(entry)
    return normalized


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
    start = _parse_time_value(raw.get("start"))
    end = _parse_time_value(raw.get("end"))
    if start is None or end is None:
        return None

    if end <= start:
        return None

    return {
        "start": round(start, 3),
        "end": round(end, 3),
    }


def _normalize_topic(raw: dict[str, Any]) -> dict[str, Any] | None:
    start = _parse_time_value(raw.get("start"))
    end = _parse_time_value(raw.get("end"))
    if start is None or end is None:
        return None

    if end <= start:
        return None

    title = str(raw.get("title") or "").strip() or "章节"
    return {
        "title": title,
        "start": round(start, 3),
        "end": round(end, 3),
    }


def _parse_time_value(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = None
    if value is not None and math.isfinite(value):
        return value
    text = str(raw or "").strip()
    match = _TIMECODE_RE.match(text)
    if not match:
        return None
    try:
        hours = int(match.group("hh"))
        minutes = int(match.group("mm"))
        seconds = int(match.group("ss"))
        milliseconds = int(match.group("ms"))
    except (TypeError, ValueError):
        return None
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0


def _normalize_subtitle_theme(raw: Any) -> str | None:
    value = str(raw or "").strip()
    if value in {"white", "box-white-on-black", "text-white"}:
        return "white"
    if value in {"black", "box-black-on-white", "text-black"}:
        return "black"
    return None


def _tokenize_caption_text(text: str, start: float, end: float) -> list[dict[str, Any]]:
    if not text:
        return []
    total = len(text)
    if total <= 0:
        return []
    duration = max(0.0, end - start)
    tokens: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(text):
        remaining = text[cursor:]
        match = re.match(r"[A-Za-z0-9]+(?:['._:-][A-Za-z0-9]+)*", remaining)
        token_text = match.group(0) if match else text[cursor]
        char_start = cursor
        char_end = cursor + len(token_text)
        tokens.append(
            {
                "text": token_text,
                "start": round(start + duration * (char_start / total), 3),
                "end": round(start + duration * (char_end / total), 3),
                "char_start": char_start,
                "char_end": char_end,
            }
        )
        cursor = char_end
    return tokens


def _build_token_meta_from_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = []
    cursor = 0
    for token in tokens:
        text = str(token.get("text") or "")
        char_start = cursor
        char_end = cursor + len(text)
        cursor = char_end
        meta.append(
            {
                **token,
                "char_start": char_start,
                "char_end": char_end,
            }
        )
    return meta


def _find_highlight_token_range(
    token_meta: list[dict[str, Any]],
    highlight_text: str,
    used_char_starts: set[int],
) -> dict[str, int] | None:
    if not highlight_text or not token_meta:
        return None
    joined = "".join(str(item.get("text") or "") for item in token_meta)
    search_from = 0
    while search_from < len(joined):
        char_start = joined.find(highlight_text, search_from)
        if char_start < 0:
            return None
        if char_start in used_char_starts:
            search_from = char_start + max(1, len(highlight_text))
            continue
        char_end = char_start + len(highlight_text)
        start_token = next(
            (
                index
                for index, item in enumerate(token_meta)
                if int(item.get("char_start") or 0) <= char_start and int(item.get("char_end") or 0) > char_start
            ),
            -1,
        )
        end_token = next(
            (
                index
                for index, item in enumerate(token_meta)
                if int(item.get("char_start") or 0) < char_end and int(item.get("char_end") or 0) >= char_end
            ),
            -1,
        )
        if start_token >= 0 and end_token >= start_token:
            used_char_starts.add(char_start)
            return {"startToken": start_token, "endToken": end_token + 1}
        search_from = char_start + max(1, len(highlight_text))
    return None


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
