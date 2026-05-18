from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_auto_cut.editing import llm_client as llm_utils
from video_auto_cut.editing.direct_prompts import build_highlight_messages
from video_auto_cut.shared.test_text_protocol import format_time, parse_timed_lines

SUBTITLE_STYLE_VERSION = "subtitle-style.v1"
SUBTITLE_RENDER_VERSION = "subtitle-render.v1"
DEFAULT_SUBTITLE_THEME = "stroke"
MAX_HIGHLIGHTS_PER_CAPTION = 2
DEFAULT_STYLE_MAX_TOKENS = 2400

_HIGHLIGHT_TEXT_COLORS = [
    "#12E8D1",
    "#FF4D9D",
    "#FFE04B",
    "#63F261",
]

_HIGHLIGHT_FONT_SCALE = 1.42


def _pick_highlight_color(caption_index: int, term_index: int) -> str:
    palette_index = (caption_index + term_index) % len(_HIGHLIGHT_TEXT_COLORS)
    return _HIGHLIGHT_TEXT_COLORS[palette_index]


def normalize_subtitle_theme(raw: Any) -> str:
    value = str(raw or "").strip()
    if value in {"stroke", "outlined", "stroke-black", "text-stroke", "black", "box-black-on-white", "text-black"}:
        return "stroke"
    if value in {"stroke-white", "outlined-white", "stroke-white-fill", "text-stroke-white", "white", "box-white-on-black", "text-white"}:
        return "stroke-white"
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


def build_sparse_highlight_text(captions: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{int(caption.get('index') or index)}\t{str(caption.get('text') or '').strip()}"
        for index, caption in enumerate(captions, start=1)
        if str(caption.get("text") or "").strip()
    )


def build_subtitle_style_messages(sparse_text: str, *, subtitle_theme: str = DEFAULT_SUBTITLE_THEME) -> list[dict[str, str]]:
    return build_highlight_messages(
        sparse_text,
        subtitle_theme=normalize_subtitle_theme(subtitle_theme),
    )


def request_subtitle_style_contract(
    *,
    captions: list[dict[str, Any]],
    subtitle_theme: str = DEFAULT_SUBTITLE_THEME,
    llm_config: dict[str, Any] | None = None,
    request_text_fn: Any | None = None,
) -> dict[str, Any]:
    normalized_theme = normalize_subtitle_theme(subtitle_theme)
    normalized_captions = _normalize_source_captions(captions)
    empty_contract = _build_empty_style_contract(normalized_captions, normalized_theme)
    if not normalized_captions:
        return empty_contract

    config = dict(llm_config or {})
    config["enable_thinking"] = False
    if not config.get("base_url") or not config.get("model"):
        return empty_contract

    sparse_text = build_sparse_highlight_text(normalized_captions)
    if not sparse_text:
        return empty_contract

    requester = request_text_fn or llm_utils.chat_completion
    try:
        raw_response = requester(
            config,
            build_subtitle_style_messages(sparse_text, subtitle_theme=normalized_theme),
        )
    except Exception:
        return empty_contract

    return _build_style_contract_from_sparse_response(
        raw_response,
        source_captions=normalized_captions,
        subtitle_theme=normalized_theme,
    )


def build_subtitle_render_v1_contract(
    *,
    captions: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    topics: list[dict[str, Any]] | None = None,
    output_name: str,
    subtitle_theme: str = DEFAULT_SUBTITLE_THEME,
    style_contract: dict[str, Any] | None = None,
    llm_config: dict[str, Any] | None = None,
    request_text_fn: Any | None = None,
) -> dict[str, Any]:
    normalized_theme = normalize_subtitle_theme(subtitle_theme)
    normalized_captions = _normalize_source_captions(captions)
    normalized_segments = _normalize_timeline_items(segments, require_title=False)
    normalized_topics = _normalize_timeline_items(topics or [], require_title=True)
    style_payload = style_contract or request_subtitle_style_contract(
        captions=normalized_captions,
        subtitle_theme=normalized_theme,
        llm_config=llm_config,
        request_text_fn=request_text_fn,
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
                "highlights": [
                    {
                        "text": term,
                        "color": _pick_highlight_color(index, term_index),
                        "fontScale": _HIGHLIGHT_FONT_SCALE,
                    }
                    for term_index, term in enumerate(normalized_terms)
                ],
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


def _build_style_contract_from_sparse_response(
    raw_response: Any,
    *,
    source_captions: list[dict[str, Any]],
    subtitle_theme: str,
) -> dict[str, Any]:
    parsed_labels = _parse_sparse_highlight_lines(raw_response, source_captions=source_captions)
    normalized: list[dict[str, Any]] = []
    for source in source_captions:
        caption_index = int(source["index"])
        normalized.append(
            {
                "start": format_time(float(source["start"])),
                "end": format_time(float(source["end"])),
                "text": str(source["text"]),
                "highlights": _normalize_highlight_terms(parsed_labels.get(caption_index), str(source["text"])),
            }
        )
    return {
        "version": SUBTITLE_STYLE_VERSION,
        "subtitleTheme": normalize_subtitle_theme(subtitle_theme),
        "captions": normalized,
    }


def _parse_sparse_highlight_lines(
    raw_response: Any,
    *,
    source_captions: list[dict[str, Any]],
) -> dict[int, list[str]]:
    response_text = _strip_code_fence_text(raw_response)
    source_by_index = {int(item["index"]): str(item["text"]) for item in source_captions}
    parsed: dict[int, list[str]] = {}
    for raw_line in response_text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        index_value, payload = _split_sparse_line(line)
        if index_value is None or index_value not in source_by_index:
            continue
        terms = _parse_sparse_highlight_terms(payload, source_text=source_by_index[index_value])
        if not terms:
            continue
        existing = parsed.get(index_value, [])
        parsed[index_value] = _normalize_highlight_terms(existing + terms, source_by_index[index_value])
    return parsed


def _strip_code_fence_text(raw_response: Any) -> str:
    text = str(raw_response or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _split_sparse_line(line: str) -> tuple[int | None, str]:
    if "	" in line:
        index_text, payload = line.split("	", 1)
    else:
        parts = line.split(None, 1)
        if len(parts) < 2:
            return None, ""
        index_text, payload = parts
    try:
        return int(str(index_text).strip()), str(payload or "").strip()
    except ValueError:
        return None, ""


def _parse_sparse_highlight_terms(payload: str, *, source_text: str) -> list[str]:
    text = str(payload or "").strip()
    if not text:
        return []
    if text in source_text:
        return [text]
    if "|" in text:
        candidates = [item.strip() for item in text.split("|")]
    else:
        candidates = [item.strip() for item in text.split()]
    return [candidate for candidate in candidates if candidate]


def _normalize_highlight_terms(raw: Any, source_text: str) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    source = str(source_text or "").strip()
    for item in raw:
        candidate = ""
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("text") or "").strip()
        if (
            not candidate
            or candidate in seen
            or candidate not in source
            or not _is_reasonable_highlight_term(candidate, source)
        ):
            continue
        normalized.append(candidate)
        seen.add(candidate)
        if len(normalized) >= MAX_HIGHLIGHTS_PER_CAPTION:
            break
    return normalized


def _is_reasonable_highlight_term(candidate: str, source_text: str) -> bool:
    source = str(source_text or "").strip()
    term = str(candidate or "").strip()
    if not term or not source:
        return False
    if term == source:
        return False
    if any(ch in term for ch in "，。、；：！？,.!?") and len(term) > 6:
        return False
    if len(term) > max(8, len(source) // 2):
        return False
    return True
