from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from video_auto_cut.editing import llm_client as llm_utils
from video_auto_cut.editing.direct_prompts import build_highlight_messages
from video_auto_cut.shared.test_text_protocol import format_time, parse_timed_lines

SUBTITLE_STYLE_VERSION = "subtitle-style.v1"
SUBTITLE_RENDER_VERSION = "subtitle-render.v1"
DEFAULT_SUBTITLE_THEME = "white"
MAX_HIGHLIGHTS_PER_CAPTION = 3
DEFAULT_STYLE_MAX_TOKENS = 2400
DEFAULT_STYLE_CHUNK_SIZE = 12


def normalize_subtitle_theme(raw: Any) -> str:
    value = str(raw or "").strip()
    if value in {"white", "box-white-on-black", "text-white"}:
        return "white"
    if value in {"black", "box-black-on-white", "text-black"}:
        return "black"
    return DEFAULT_SUBTITLE_THEME


def build_subtitle_style_llm_config(
    *,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    timeout: int | float,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    resolved_max_tokens = int(max_tokens) if max_tokens is not None else DEFAULT_STYLE_MAX_TOKENS
    return llm_utils.build_llm_config(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=int(timeout),
        temperature=0.0,
        max_tokens=resolved_max_tokens,
        enable_thinking=False,
    )


def build_timed_caption_text(captions: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"【{format_time(float(caption['start']))}-{format_time(float(caption['end']))}】{str(caption.get('text') or '').strip()}"
        for caption in captions
        if str(caption.get("text") or "").strip()
    )


def build_subtitle_style_messages(timed_text: str, *, subtitle_theme: str = DEFAULT_SUBTITLE_THEME) -> list[dict[str, str]]:
    return build_highlight_messages(
        timed_text,
        subtitle_theme=normalize_subtitle_theme(subtitle_theme),
    )


def request_subtitle_style_contract(
    *,
    captions: list[dict[str, Any]],
    subtitle_theme: str = DEFAULT_SUBTITLE_THEME,
    llm_config: dict[str, Any] | None = None,
    request_json_fn: Any | None = None,
) -> dict[str, Any]:
    normalized_theme = normalize_subtitle_theme(subtitle_theme)
    normalized_captions = _normalize_source_captions(captions)
    empty_contract = _build_empty_style_contract(normalized_captions, normalized_theme)
    if not normalized_captions:
        return empty_contract

    config = llm_config or {}
    if not config.get("base_url") or not config.get("model"):
        return empty_contract

    requester = request_json_fn or llm_utils.request_json
    merged_captions: list[dict[str, Any]] = []
    for chunk in _chunk_captions(normalized_captions):
        timed_text = build_timed_caption_text(chunk)
        if not timed_text:
            continue
        try:
            payload = requester(
                config,
                build_subtitle_style_messages(timed_text, subtitle_theme=normalized_theme),
                validate=lambda raw_payload, source_chunk=chunk: _validate_style_payload(
                    raw_payload,
                    source_captions=source_chunk,
                    subtitle_theme=normalized_theme,
                ),
                repair_retries=1,
                repair_instructions=(
                    "Return one JSON object only. Keep every caption row in the same order with the same "
                    "`start`, `end`, and `text` values as the input. Each caption may only contain a `highlights` "
                    "array of original text fragments."
                ),
            )
            merged_captions.extend(list(payload.get("captions") or []))
        except Exception:
            merged_captions.extend(_build_empty_style_contract(chunk, normalized_theme)["captions"])

    if len(merged_captions) != len(normalized_captions):
        return empty_contract

    return {
        "version": SUBTITLE_STYLE_VERSION,
        "subtitleTheme": normalized_theme,
        "captions": merged_captions,
    }


def build_subtitle_render_v1_contract(
    *,
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    topics: list[dict[str, Any]] | None = None,
    output_name: str,
    subtitle_theme: str = DEFAULT_SUBTITLE_THEME,
    style_contract: dict[str, Any] | None = None,
    llm_config: dict[str, Any] | None = None,
    request_json_fn: Any | None = None,
) -> dict[str, Any]:
    normalized_theme = normalize_subtitle_theme(subtitle_theme)
    normalized_captions = _normalize_source_captions(captions)
    normalized_segments = _normalize_timeline_items(segments, require_title=False)
    normalized_topics = _normalize_timeline_items(topics or [], require_title=True)
    style_payload = style_contract or request_subtitle_style_contract(
        captions=normalized_captions,
        subtitle_theme=normalized_theme,
        llm_config=llm_config,
        request_json_fn=request_json_fn,
    )
    style_captions = list(style_payload.get("captions") or [])

    render_captions: list[dict[str, Any]] = []
    for index, caption in enumerate(normalized_captions):
        entry: dict[str, Any] = {
            "index": int(caption.get("index") or index + 1),
            "start": float(caption["start"]),
            "end": float(caption["end"]),
            "text": str(caption["text"]),
        }
        if isinstance(caption.get("tokens"), list) and caption["tokens"]:
            entry["tokens"] = caption["tokens"]
        alignment_mode = str(caption.get("alignmentMode") or "").strip()
        if alignment_mode in {"exact", "fuzzy", "degraded", "missing"}:
            entry["alignmentMode"] = alignment_mode

        highlight_terms = []
        if index < len(style_captions) and isinstance(style_captions[index], dict):
            highlight_terms = list(style_captions[index].get("highlights") or [])
        normalized_terms = _normalize_highlight_terms(highlight_terms, entry["text"])
        if normalized_terms:
            entry["label"] = {
                "highlights": [{"text": term} for term in normalized_terms],
            }
        render_captions.append(entry)

    return {
        "version": SUBTITLE_RENDER_VERSION,
        "subtitleTheme": normalized_theme,
        "output_name": str(output_name or "subtitle-render_export.mp4").strip() or "subtitle-render_export.mp4",
        "captions": render_captions,
        "segments": normalized_segments,
        "topics": normalized_topics,
    }


def write_subtitle_render_v1_contract(contract: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_timed_captions_from_text(source_path: Path) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for index, (start, end, remove, text) in enumerate(
        parse_timed_lines(source_path.read_text(encoding="utf-8")),
        start=1,
    ):
        if remove:
            continue
        normalized_text = str(text or "").strip()
        if not normalized_text:
            continue
        captions.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "text": normalized_text,
            }
        )
    return captions


def _build_empty_style_contract(captions: list[dict[str, Any]], subtitle_theme: str) -> dict[str, Any]:
    return {
        "version": SUBTITLE_STYLE_VERSION,
        "subtitleTheme": subtitle_theme,
        "captions": [
            {
                "start": format_time(float(caption["start"])),
                "end": format_time(float(caption["end"])),
                "text": str(caption["text"]),
                "highlights": [],
            }
            for caption in captions
        ],
    }


def _chunk_captions(captions: list[dict[str, Any]], chunk_size: int = DEFAULT_STYLE_CHUNK_SIZE) -> list[list[dict[str, Any]]]:
    resolved_size = max(1, int(chunk_size))
    return [captions[index : index + resolved_size] for index in range(0, len(captions), resolved_size)]


def _normalize_source_captions(captions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, caption in enumerate(captions, start=1):
        if not isinstance(caption, dict):
            continue
        text = str(caption.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(caption["start"])
            end = float(caption["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        entry: dict[str, Any] = {
            "index": int(caption.get("index") or index),
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        }
        if isinstance(caption.get("tokens"), list):
            entry["tokens"] = caption["tokens"]
        if caption.get("alignmentMode") is not None:
            entry["alignmentMode"] = caption["alignmentMode"]
        normalized.append(entry)
    return normalized


def _normalize_timeline_items(
    items: list[dict[str, Any]],
    *,
    require_title: bool,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        entry: dict[str, Any] = {
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if require_title:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            entry["title"] = title
        normalized.append(entry)
    return normalized


def _validate_style_payload(
    payload: dict[str, Any],
    *,
    source_captions: list[dict[str, Any]],
    subtitle_theme: str,
) -> dict[str, Any]:
    raw_captions = payload.get("captions")
    if not isinstance(raw_captions, list):
        raise RuntimeError("Subtitle style payload must contain a `captions` array.")
    if len(raw_captions) != len(source_captions):
        raise RuntimeError("Subtitle style payload must cover every input caption row.")

    normalized: list[dict[str, Any]] = []
    for source, raw_caption in zip(source_captions, raw_captions):
        if not isinstance(raw_caption, dict):
            raise RuntimeError("Every style caption entry must be an object.")
        start = _coerce_payload_time(raw_caption.get("start"))
        end = _coerce_payload_time(raw_caption.get("end"))
        if start is None or end is None:
            raise RuntimeError("Style payload caption is missing `start`/`end`.")
        if abs(start - float(source["start"])) > 0.001 or abs(end - float(source["end"])) > 0.001:
            raise RuntimeError("Style payload caption timing does not match the input row.")
        text = str(raw_caption.get("text") or "").strip()
        if text != str(source["text"]):
            raise RuntimeError("Style payload caption text must match the input row.")
        normalized.append(
            {
                "start": format_time(float(source["start"])),
                "end": format_time(float(source["end"])),
                "text": str(source["text"]),
                "highlights": _normalize_highlight_terms(raw_caption.get("highlights"), str(source["text"])),
            }
        )

    return {
        "version": SUBTITLE_STYLE_VERSION,
        "subtitleTheme": normalize_subtitle_theme(payload.get("subtitleTheme") or subtitle_theme),
        "captions": normalized,
    }


def _normalize_highlight_terms(raw: Any, source_text: str) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        candidate = ""
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("text") or "").strip()
        if not candidate or candidate in seen or candidate not in source_text:
            continue
        normalized.append(candidate)
        seen.add(candidate)
        if len(normalized) >= MAX_HIGHLIGHTS_PER_CAPTION:
            break
    return normalized


def _coerce_payload_time(raw: Any) -> float | None:
    try:
        value = float(raw)
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    text = str(raw or "").strip()
    if len(text) == 12 and text[2] == ":" and text[5] == ":" and text[8] == ".":
        try:
            hours = int(text[0:2])
            minutes = int(text[3:5])
            seconds = int(text[6:8])
            milliseconds = int(text[9:12])
        except ValueError:
            return None
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return None
