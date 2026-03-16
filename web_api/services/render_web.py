from __future__ import annotations

import logging
import math
import re
from typing import Any

from video_auto_cut.editing import llm_client as llm_utils
from video_auto_cut.editing.topic_segment import (
    BAD_TITLE_ENDING_PATTERN,
    GENERIC_SECTION_TITLE_PATTERN,
    PLACEHOLDER_TITLE_PATTERN,
)
from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt

from ..config import ensure_job_dirs, get_settings
from ..constants import DEFAULT_ENCODING
from ..repository import get_job_files, list_step2_chapters

REFERENCE_WIDTH = 1920.0
REFERENCE_HEIGHT = 1080.0
SCALE_EXPONENT = 0.72
CJK_RE = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]")
BREAK_PUNCT_RE = re.compile(r"[，。！？；：、,.!?;:…—]")
EM_DASH_RE = re.compile(r"[—―－]")
SPACE_RE = re.compile(r"\s+")


def _clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _round_int(value: float) -> int:
    return max(0, int(math.floor(float(value) + 0.5)))


def _at_least(value: int, minimum: int) -> int:
    return max(int(value), int(minimum))


def _scale_from_reference(value: float, reference: float) -> float:
    return math.pow(max(1.0, float(value)) / float(reference), SCALE_EXPONENT)


def _scale_dimension(base: float, scale: float, minimum: int) -> int:
    return _at_least(_round_int(base * scale), minimum)


def _char_units(char: str) -> float:
    if char in {" ", "\t"}:
        return 0.35
    if EM_DASH_RE.search(char):
        return 1.05
    if char == "…":
        return 1.0
    if BREAK_PUNCT_RE.search(char):
        return 0.6
    if char.isascii() and char.isalnum():
        return 0.56
    if CJK_RE.search(char):
        return 1.0
    return 0.75


def _measure_text_width(text: str, font_size: int) -> float:
    normalized = str(text or "").strip()
    if not normalized:
        return 0.0
    units = sum(_char_units(char) for char in normalized)
    return units * max(1, int(font_size)) * 1.02


def _build_progress_typography(width: int, height: int) -> dict[str, int]:
    resolved_width = max(1, int(width))
    resolved_height = max(1, int(height))
    aspect_ratio = resolved_width / resolved_height
    portrait_strength = _clamp((0.82 - aspect_ratio) / 0.32, 0.0, 1.0)
    vertical_scale = _scale_from_reference(resolved_height, REFERENCE_HEIGHT)
    horizontal_scale = _scale_from_reference(resolved_width, REFERENCE_WIDTH)
    progress_scale = vertical_scale * (1.0 + portrait_strength * 0.18)
    progress_label_font_size = _scale_dimension(18.2, progress_scale, 17)
    progress_height = max(
        _scale_dimension(42, progress_scale, 34),
        _round_int(progress_label_font_size * 2.25),
    )
    return {
        "progressInsetX": _scale_dimension(44, horizontal_scale, 20),
        "progressHeight": progress_height,
        "progressLabelPaddingX": _scale_dimension(4, progress_scale, 3),
        "progressLabelFontSize": progress_label_font_size,
    }


def _resolve_total_duration(
    topics: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> float:
    topic_end = max((float(item["end"]) for item in topics), default=0.0)
    caption_end = max((float(item["end"]) for item in captions), default=0.0)
    segment_end = max((float(item["end"]) for item in segments), default=0.0)
    return max(1.0, topic_end, caption_end, segment_end)


def _fit_uniform_progress_font(
    topics: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    min_font_size: int | None = None,
) -> dict[str, Any]:
    typography = _build_progress_typography(width, height)
    progress_inner_width = max(1.0, float(width) - typography["progressInsetX"] * 2.0)
    total_duration = _resolve_total_duration(topics, captions, segments)
    base_font_size = int(typography["progressLabelFontSize"])
    readable_min_font = max(12, math.floor(base_font_size * 0.45))
    resolved_min_font = max(readable_min_font, int(min_font_size or readable_min_font))
    max_font_size = max(base_font_size, math.floor(typography["progressHeight"] * 0.58))
    horizontal_padding = max(0, int(typography["progressLabelPaddingX"]))
    target_width_ratio = 0.84
    segment_metrics: list[dict[str, Any]] = []

    for topic in topics:
        start_ratio = _clamp(float(topic["start"]) / total_duration, 0.0, 1.0)
        end_ratio = _clamp(float(topic["end"]) / total_duration, 0.0, 1.0)
        if end_ratio <= start_ratio:
            continue
        segment_width = progress_inner_width * (end_ratio - start_ratio)
        usable_width = max(0.0, segment_width - horizontal_padding * 2.0)
        normalized_title = str(topic.get("title") or "").strip()
        min_width = _measure_text_width(normalized_title, resolved_min_font)
        natural_width_at_one = max(0.0001, _measure_text_width(normalized_title, 1))
        width_driven_max_font = _at_least(math.floor(usable_width / natural_width_at_one), resolved_min_font)
        segment_metrics.append(
            {
                "title": normalized_title,
                "segment_width": segment_width,
                "usable_width": usable_width,
                "target_width": max(1.0, usable_width * target_width_ratio),
                "visible": bool(normalized_title) and min_width <= usable_width,
                "resolved_max_font": min(width_driven_max_font, max_font_size),
            }
        )

    if not segment_metrics:
        return {
            "font_size": resolved_min_font,
            "base_font_size": base_font_size,
            "readable_min_font": readable_min_font,
            "segment_metrics": [],
            "fits_all": True,
        }

    if any(not item["visible"] for item in segment_metrics):
        return {
            "font_size": resolved_min_font,
            "base_font_size": base_font_size,
            "readable_min_font": readable_min_font,
            "segment_metrics": segment_metrics,
            "fits_all": False,
        }

    low = resolved_min_font
    high = max(resolved_min_font, min(int(item["resolved_max_font"]) for item in segment_metrics))
    best = (
        resolved_min_font
        if all(
            _measure_text_width(str(item["title"]), resolved_min_font) <= float(item["target_width"])
            for item in segment_metrics
        )
        else 0
    )

    while low <= high:
        mid = math.floor((low + high) / 2)
        if all(
            _measure_text_width(str(item["title"]), mid) <= float(item["target_width"])
            for item in segment_metrics
        ):
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    return {
        "font_size": best if best > 0 else resolved_min_font,
        "base_font_size": base_font_size,
        "readable_min_font": readable_min_font,
        "segment_metrics": segment_metrics,
        "fits_all": True,
    }


def _build_render_title_budgets(
    fit_result: dict[str, Any],
    target_font_size: int,
    max_chars_cap: int,
) -> list[int]:
    budgets: list[int] = []
    resolved_cap = max(2, int(max_chars_cap))
    for item in fit_result.get("segment_metrics", []):
        target_width = max(1.0, float(item.get("target_width", 0.0)))
        max_units = max(2, math.floor(target_width / max(1.0, target_font_size) / 1.02))
        budgets.append(max(2, min(resolved_cap, max_units)))
    return budgets


def _collect_topic_context(topic: dict[str, Any], captions: list[dict[str, Any]], limit: int = 80) -> str:
    start = float(topic["start"])
    end = float(topic["end"])
    parts: list[str] = []
    total_chars = 0
    for caption in captions:
        caption_start = float(caption["start"])
        caption_end = float(caption["end"])
        if caption_end <= start or caption_start >= end:
            continue
        text = SPACE_RE.sub(" ", str(caption.get("text") or "").strip())
        if not text:
            continue
        remaining = max(0, limit - total_chars)
        if remaining <= 0:
            break
        snippet = text[:remaining]
        parts.append(snippet)
        total_chars += len(snippet)
        if total_chars >= limit:
            break
    return " ".join(parts).strip()


def _find_render_title_issues(titles: list[str], budgets: list[int]) -> list[str]:
    if len(titles) != len(budgets):
        return [f"标题数量不匹配：期望 {len(budgets)} 个，实际 {len(titles)} 个。"]

    issues: list[str] = []
    for index, (title, budget) in enumerate(zip(titles, budgets), start=1):
        value = SPACE_RE.sub(" ", str(title or "").strip())
        if not value:
            issues.append(f"第 {index} 个标题为空。")
            continue
        if len(value) > max(2, int(budget)):
            issues.append(f"第 {index} 个标题超出 {budget} 字上限：{value}")
        if PLACEHOLDER_TITLE_PATTERN.match(value) or GENERIC_SECTION_TITLE_PATTERN.match(value):
            issues.append(f"第 {index} 个标题仍是占位词或空泛标题：{value}")
        if BAD_TITLE_ENDING_PATTERN.search(value):
            issues.append(f"第 {index} 个标题像半句话，以虚词结尾：{value}")
    return issues


def _validate_render_titles(titles: list[str], budgets: list[int]) -> list[str] | None:
    issues = _find_render_title_issues(titles, budgets)
    if issues:
        return None

    normalized: list[str] = []
    for title, budget in zip(titles, budgets):
        value = SPACE_RE.sub(" ", str(title or "").strip())
        if not value:
            return None
        if len(value) > max(2, int(budget)):
            return None
        if PLACEHOLDER_TITLE_PATTERN.match(value) or GENERIC_SECTION_TITLE_PATTERN.match(value):
            return None
        if BAD_TITLE_ENDING_PATTERN.search(value):
            return None
        normalized.append(value)
    return normalized


def _rewrite_render_titles(
    topics: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    *,
    budgets: list[int],
    settings: Any,
    chat_completion_fn: Any | None = None,
) -> list[str] | None:
    if len(topics) != len(budgets):
        return None
    llm_config = llm_utils.build_llm_config(
        base_url=getattr(settings, "llm_base_url", None),
        model=getattr(settings, "llm_model", None),
        api_key=getattr(settings, "llm_api_key", None),
        timeout=getattr(settings, "llm_timeout", 60),
        temperature=getattr(settings, "llm_temperature", 0.2),
        max_tokens=getattr(settings, "llm_max_tokens", None),
        enable_thinking=False,
    )
    if not llm_config.get("base_url") or not llm_config.get("model"):
        return None

    payload_lines: list[str] = []
    for index, (topic, budget) in enumerate(zip(topics, budgets), start=1):
        payload_lines.append(
            (
                f"[{index}] 原标题：{topic['title']}\n"
                f"字数上限：{budget}\n"
                f"上下文：{_collect_topic_context(topic, captions) or '无'}"
            )
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频章节标题精修器。"
                "任务是把每一章标题改写成更短、更适合底部章节进度条上屏的标题。"
                "保持原意，不要解释，不要输出 markdown，只输出严格 JSON。"
                '格式：{"titles":["标题1","标题2"]}。'
                "要求：标题像视频章节导航；短、稳、好懂；避免空泛占位词；"
                "不要以“的/了/和/及/与”结尾；必须严格遵守每章给定的字数上限。"
                "优先保留原标题或上下文里的核心词，不要为了变短而硬造新词。"
                "允许删减，但不要把两个词机械拼接成生硬缩写。"
                "输出必须是自然、常见、能被用户一眼看懂的中文短标题。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按原顺序改写以下章节标题，返回相同数量的 titles：\n\n"
                + "\n\n".join(payload_lines)
            ),
        },
    ]

    chat_fn = chat_completion_fn or llm_utils.chat_completion
    issues: list[str] = []
    previous_raw = ""

    for attempt in range(2):
        attempt_messages = list(messages)
        if attempt > 0:
            retry_prompt = (
                "上一版输出没有通过校验，请重写完整 titles JSON。\n"
                f"上一版输出：{previous_raw}\n"
                "问题：\n"
                + "\n".join(f"- {issue}" for issue in issues)
            )
            attempt_messages.append({"role": "user", "content": retry_prompt})
        try:
            raw = chat_fn(llm_config, attempt_messages)
            previous_raw = raw
            data = llm_utils.extract_json(raw)
            titles = data.get("titles")
            if not isinstance(titles, list):
                issues = ["输出缺少 titles 数组。"]
                continue
            normalized_titles = [str(item) for item in titles]
            validated = _validate_render_titles(normalized_titles, budgets)
            if validated:
                return validated
            issues = _find_render_title_issues(normalized_titles, budgets)
        except Exception as exc:
            logging.warning("Render title rewrite attempt %d failed: %s", attempt + 1, exc)
            issues = [str(exc)]
    return None


def _prepare_render_topics(
    topics: list[dict[str, Any]],
    *,
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    width: int,
    height: int,
    settings: Any,
    chat_completion_fn: Any | None = None,
) -> list[dict[str, Any]]:
    if len(topics) <= 1:
        return topics

    original_fit = _fit_uniform_progress_font(
        topics,
        width=width,
        height=height,
        captions=captions,
        segments=segments,
    )
    preferred_min_font = max(
        int(original_fit["readable_min_font"]),
        math.floor(int(original_fit["base_font_size"]) * 0.8),
    )
    if bool(original_fit["fits_all"]) and int(original_fit["font_size"]) >= preferred_min_font:
        return topics

    budgets = _build_render_title_budgets(
        original_fit,
        target_font_size=preferred_min_font,
        max_chars_cap=getattr(settings, "topic_title_max_chars", 6),
    )
    rewritten_titles = _rewrite_render_titles(
        topics,
        captions,
        budgets=budgets,
        settings=settings,
        chat_completion_fn=chat_completion_fn,
    )
    if not rewritten_titles:
        return topics

    rewritten_topics = [{**topic, "title": title} for topic, title in zip(topics, rewritten_titles)]
    rewritten_fit = _fit_uniform_progress_font(
        rewritten_topics,
        width=width,
        height=height,
        captions=captions,
        segments=segments,
    )
    if int(rewritten_fit["font_size"]) >= int(original_fit["font_size"]):
        return rewritten_topics
    return topics


def build_web_render_config(
    job_id: str,
    *,
    fps: float | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_sec: float | None = None,
    chat_completion_fn: Any | None = None,
) -> dict[str, Any]:
    files = get_job_files(job_id)
    if not files:
        raise RuntimeError("job files not found for render")

    step1_srt_path = files.get("final_step1_srt_path")
    if not step1_srt_path:
        raise RuntimeError("render inputs missing")

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

    resolved_fps = _resolve_fps(fps)
    resolved_width, resolved_height = _resolve_dimensions(width, height)
    topics = _prepare_render_topics(
        topics,
        captions=captions,
        segments=segments,
        width=resolved_width,
        height=resolved_height,
        settings=settings,
        chat_completion_fn=chat_completion_fn,
    )
    segment_duration_in_frames = _duration_frames_from_segments(segments, resolved_fps)
    if segment_duration_in_frames > 0:
        duration_in_frames = segment_duration_in_frames
    else:
        resolved_duration_s = _resolve_duration(duration_sec, captions, segments)
        duration_in_frames = max(1, int(math.ceil(resolved_duration_s * resolved_fps)))

    output_name = f"{job_id}_export.mp4"
    input_props: dict[str, Any] = {
        # Always replaced by browser-side blob URL in frontend.
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


def _resolve_dimensions(
    override_width: int | None,
    override_height: int | None,
) -> tuple[int, int]:
    if override_width is None or override_height is None:
        raise ValueError("width and height are required to build render config")
    try:
        width = int(override_width)
        height = int(override_height)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid width/height: {override_width}, {override_height}") from exc

    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive, got {width}x{height}")

    return _ensure_even(width), _ensure_even(height)


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


def _ensure_even(value: int) -> int:
    if value <= 2:
        return 2
    if value % 2 == 0:
        return value
    return value - 1
