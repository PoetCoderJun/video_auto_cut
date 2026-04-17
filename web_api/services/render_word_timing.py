from __future__ import annotations

import re
from typing import Any

import srt

from video_auto_cut.asr.word_timing_sidecar import load_sidecar

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['._:-][A-Za-z0-9]+)*")
_WHITESPACE_RE = re.compile(r"\s+")


def attach_remapped_tokens_to_captions(
    *,
    captions: list[dict[str, Any]],
    kept_subtitles: list[srt.Subtitle],
    segments: list[dict[str, Any]],
    sidecar_path: str | None,
) -> list[dict[str, Any]]:
    sidecar = load_sidecar(sidecar_path) if sidecar_path else None
    if not sidecar:
        return captions

    words = [item for item in list(sidecar.get("words") or []) if _normalize_sidecar_word(item) is not None]
    normalized_words = [_normalize_sidecar_word(item) for item in words]
    normalized_words = [item for item in normalized_words if item is not None]
    if not normalized_words:
        return captions

    captions_by_index = {int(item["index"]): item for item in captions if "index" in item}
    remapped = []
    for subtitle in kept_subtitles:
        try:
            caption_index = int(subtitle.index)
        except Exception:
            continue
        caption = captions_by_index.get(caption_index)
        if caption is None:
            continue
        tokens, alignment_mode = _remap_caption_tokens(
            subtitle=subtitle,
            caption=caption,
            segments=segments,
            words=normalized_words,
        )
        enriched = dict(caption)
        if tokens:
            enriched["tokens"] = tokens
            enriched["alignmentMode"] = alignment_mode
        remapped.append(enriched)

    if len(remapped) != len(captions):
        remapped_map = {int(item["index"]): item for item in remapped if "index" in item}
        return [remapped_map.get(int(item["index"]), item) for item in captions]
    return remapped


def _remap_caption_tokens(
    *,
    subtitle: srt.Subtitle,
    caption: dict[str, Any],
    segments: list[dict[str, Any]],
    words: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    subtitle_start = float(subtitle.start.total_seconds())
    subtitle_end = float(subtitle.end.total_seconds())
    caption_start = float(caption["start"])
    caption_end = float(caption["end"])
    source_words = [
        word
        for word in words
        if word["end_s"] > subtitle_start - 0.04 and word["start_s"] < subtitle_end + 0.04
    ]
    target_text = str(subtitle.content or "").strip()
    if source_words:
        return (
            _build_estimated_tokens(
                target_text,
                caption_start,
                caption_end,
                skeleton_times=[(word["start_s"], word["end_s"]) for word in source_words],
                segments=segments,
                source_word_indexes=[int(word["index"]) for word in source_words],
            ),
            "fuzzy",
        )
    return _build_estimated_tokens(target_text, caption_start, caption_end), "fuzzy"


def _build_estimated_tokens(
    text: str,
    caption_start: float,
    caption_end: float,
    *,
    skeleton_times: list[tuple[float, float]] | None = None,
    segments: list[dict[str, Any]] | None = None,
    source_word_indexes: list[int] | None = None,
) -> list[dict[str, Any]]:
    target_tokens = _tokenize_text(text)
    if not target_tokens:
        return []

    if skeleton_times:
        skeleton_guided = _build_skeleton_guided_tokens(
            target_tokens=target_tokens,
            skeleton_times=skeleton_times,
            caption_start=caption_start,
            caption_end=caption_end,
            segments=segments,
            source_word_indexes=source_word_indexes,
        )
        if skeleton_guided:
            return skeleton_guided

    duration = max(0.001, caption_end - caption_start)
    total_weight = sum(item["weight"] for item in target_tokens) or 1.0
    cursor = caption_start
    output: list[dict[str, Any]] = []
    for index, token in enumerate(target_tokens):
        token_duration = duration * (token["weight"] / total_weight)
        start = cursor
        end = caption_end if index == len(target_tokens) - 1 else min(caption_end, cursor + token_duration)
        output.append(
            {
                "text": token["text"],
                "start": round(start, 3),
                "end": round(max(start, end), 3),
            }
        )
        cursor = end
    return _normalize_token_bounds(output, caption_start, caption_end)


def _build_skeleton_guided_tokens(
    *,
    target_tokens: list[dict[str, Any]],
    skeleton_times: list[tuple[float, float]],
    caption_start: float,
    caption_end: float,
    segments: list[dict[str, Any]] | None = None,
    source_word_indexes: list[int] | None = None,
) -> list[dict[str, Any]]:
    if not target_tokens or not skeleton_times:
        return []

    mapped_windows: list[tuple[float, float]] = []
    for start_s, end_s in skeleton_times:
        start = float(start_s)
        end = max(start, float(end_s))
        if segments:
            start = _map_original_time_to_cut_time(start, segments, prefer_end=False)
            end = _map_original_time_to_cut_time(end, segments, prefer_end=True)
        mapped_windows.append((start, max(start, end)))

    if not mapped_windows:
        return []

    boundaries = [mapped_windows[0][0], *[window_end for _, window_end in mapped_windows]]
    monotonic_boundaries: list[float] = []
    cursor = boundaries[0]
    for boundary in boundaries:
        cursor = max(cursor, float(boundary))
        monotonic_boundaries.append(cursor)

    skeleton_span_count = len(monotonic_boundaries) - 1
    output: list[dict[str, Any]] = []
    for index, token in enumerate(target_tokens):
        start = _interpolate_skeleton_boundary(
            monotonic_boundaries,
            (index * skeleton_span_count) / len(target_tokens),
        )
        end = _interpolate_skeleton_boundary(
            monotonic_boundaries,
            ((index + 1) * skeleton_span_count) / len(target_tokens),
        )
        token_payload = {
            "text": token["text"],
            "start": round(start, 3),
            "end": round(max(start, end), 3),
        }
        if source_word_indexes:
            source_index = source_word_indexes[
                min(
                    len(source_word_indexes) - 1,
                    int(index * skeleton_span_count / len(target_tokens)),
                )
            ]
            token_payload["sourceWordIndex"] = source_index
        output.append(token_payload)
    return _normalize_token_bounds(output, caption_start, caption_end)


def _interpolate_skeleton_boundary(boundaries: list[float], position: float) -> float:
    if not boundaries:
        return 0.0
    if len(boundaries) == 1 or position <= 0:
        return float(boundaries[0])

    last_index = len(boundaries) - 1
    if position >= last_index:
        return float(boundaries[-1])

    left_index = int(position)
    right_index = min(last_index, left_index + 1)
    fraction = position - left_index
    left = float(boundaries[left_index])
    right = float(boundaries[right_index])
    return left + ((right - left) * fraction)


def _normalize_token_bounds(
    tokens: list[dict[str, Any]],
    caption_start: float,
    caption_end: float,
) -> list[dict[str, Any]]:
    if not tokens:
        return []
    resolved: list[dict[str, Any]] = []
    cursor = round(caption_start, 3)
    for index, token in enumerate(tokens):
        start = max(cursor, round(float(token.get("start") or cursor), 3))
        end = round(float(token.get("end") or start), 3)
        if index == len(tokens) - 1:
            end = round(caption_end, 3)
        min_duration = 0.001
        if end < start:
            end = start
        if end == start and caption_end > caption_start:
            next_end = round(min(caption_end, start + min_duration), 3)
            end = next_end if index < len(tokens) - 1 else round(caption_end, 3)
        token_copy = dict(token)
        token_copy["start"] = start
        token_copy["end"] = min(round(caption_end, 3), max(start, end))
        resolved.append(token_copy)
        cursor = token_copy["end"]
    resolved[0]["start"] = round(caption_start, 3)
    resolved[-1]["end"] = round(caption_end, 3)
    return [item for item in resolved if str(item.get("text") or "").strip()]


def _tokenize_text(text: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    content = _WHITESPACE_RE.sub("", str(text or ""))
    position = 0
    while position < len(content):
        ascii_match = _ASCII_TOKEN_RE.match(content, position)
        if ascii_match:
            token_text = ascii_match.group(0)
            output.append({"text": token_text, "weight": max(1.0, len(token_text) * 0.55)})
            position = ascii_match.end()
            continue
        char = content[position]
        if _is_punctuation(char) and output:
            output[-1]["text"] = f"{output[-1]['text']}{char}"
            output[-1]["weight"] += 0.2
        else:
            output.append({"text": char, "weight": 0.35 if _is_punctuation(char) else 1.0})
        position += 1
    return output


def _normalize_sidecar_word(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        start_ms = int(item.get("start_ms"))
        end_ms = int(item.get("end_ms"))
        index = int(item.get("index"))
    except (TypeError, ValueError):
        return None
    if start_ms < 0 or end_ms < start_ms:
        return None
    text = str(item.get("text") or "")
    punct = str(item.get("punct") or "")
    if not text and not punct:
        return None
    return {
        "index": index,
        "text": text,
        "punct": punct,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start_s": start_ms / 1000.0,
        "end_s": end_ms / 1000.0,
    }


def _is_punctuation(char: str) -> bool:
    return char in "，。！？；：,.!?;:"


def _map_original_time_to_cut_time(
    time_sec: float,
    segments: list[dict[str, Any]],
    *,
    prefer_end: bool,
) -> float:
    timeline = _build_cut_timeline(segments)
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


def _build_cut_timeline(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    cursor = 0.0
    timeline: list[dict[str, float]] = []
    for item in sorted(segments, key=lambda seg: float(seg["start"])):
        start = float(item["start"])
        end = float(item["end"])
        if end <= start:
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
