from __future__ import annotations

import json
import logging
from typing import Any

from video_auto_cut.editing import llm_client as llm_utils

from ..config import get_settings

_DEFAULT_LABEL_MAX_TOKENS = 600
_MAX_HIGHLIGHTS = 3
_MAX_BADGE_TEXT_LENGTH = 16
_MAX_EMPHASIS_SPANS = 3
_DEFAULT_HIGHLIGHT_COLORS = ("#22c55e", "#38bdf8", "#f59e0b")
_DEFAULT_HIGHLIGHT_SCALES = (1.24, 1.18, 1.14)


def attach_llm_labels_to_captions(
    *,
    captions: list[dict[str, Any]],
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    eligible_captions = [item for item in captions if _has_caption_tokens(item)]
    if not eligible_captions:
        return captions

    llm_config = _build_caption_label_llm_config()
    if not llm_config.get("base_url") or not llm_config.get("model"):
        return captions

    captions_by_index = {int(item["index"]): item for item in eligible_captions}
    try:
        payload = llm_utils.request_json(
            llm_config,
            _build_label_messages(eligible_captions),
            validate=lambda data: _validate_label_payload(data, captions_by_index),
            repair_retries=1,
            repair_instructions=(
                "Return one JSON object with a `labels` array. "
                "Each item must use an existing caption `index` and should prefer "
                "`highlights` with `startToken`/`endToken` or exact `text`. "
                "Legacy `badgeText` and `emphasisSpans` are accepted only as fallback."
            ),
        )
    except Exception as exc:
        logging.warning(
            "Render caption labeling skipped%s: %s",
            f" for job {job_id}" if job_id else "",
            exc,
        )
        return captions

    labels_by_index = {
        int(item["index"]): item["label"]
        for item in list(payload.get("labels") or [])
        if isinstance(item, dict) and isinstance(item.get("label"), dict)
    }
    if not labels_by_index:
        return captions

    enriched_captions: list[dict[str, Any]] = []
    for caption in captions:
        label = labels_by_index.get(int(caption.get("index") or 0))
        if label is None:
            enriched_captions.append(caption)
            continue
        enriched = dict(caption)
        enriched["label"] = label
        enriched_captions.append(enriched)
    return enriched_captions


def _build_caption_label_llm_config() -> dict[str, Any]:
    settings = get_settings()
    max_tokens = settings.llm_max_tokens
    if max_tokens is None:
        max_tokens = _DEFAULT_LABEL_MAX_TOKENS
    return llm_utils.build_llm_config(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=int(settings.llm_timeout),
        temperature=0.0,
        max_tokens=max_tokens,
        enable_thinking=False,
    )


def _build_label_messages(captions: list[dict[str, Any]]) -> list[dict[str, str]]:
    prompt_payload = {
        "captions": [
            {
                "index": int(item["index"]),
                "text": str(item.get("text") or ""),
                "tokens": [
                    {
                        "index": token_index,
                        "text": str(token.get("text") or ""),
                    }
                    for token_index, token in enumerate(list(item.get("tokens") or []))
                ],
            }
            for item in captions
        ]
    }
    return [
        {
            "role": "system",
            "content": (
                "You label short video captions for later rendering. "
                "Return JSON only. Prefer a single schema: "
                "{\"labels\":[{\"index\":1,\"highlights\":[{\"startToken\":0,\"endToken\":2,\"text\":\"重点结论\",\"color\":\"#22c55e\",\"fontScale\":1.18}]}]}. "
                "If a caption does not need a label, omit it. "
                "Be decisive instead of conservative. Highlight the words or short phrases that carry "
                "tone, conclusion, contrast, action, product terms, numbers, results, or turning points. "
                "Prefer 1-3 highlights per caption when there is an obvious focus. "
                "Prefer highlights over badgeText or emphasisSpans, do not invent abstract badge labels, "
                "keep highlight text exact, use endToken exclusive, and provide color plus fontScale for every highlight."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(prompt_payload, ensure_ascii=False),
        },
    ]


def _validate_label_payload(
    payload: dict[str, Any],
    captions_by_index: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    raw_labels = payload.get("labels")
    if raw_labels is None:
        return {"labels": []}
    if not isinstance(raw_labels, list):
        raise RuntimeError("LLM response missing `labels` array.")

    normalized: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for raw_label in raw_labels:
        if not isinstance(raw_label, dict):
            continue
        caption_index = _coerce_int(raw_label.get("index"))
        if caption_index is None or caption_index in seen_indexes:
            continue
        caption = captions_by_index.get(caption_index)
        if caption is None:
            continue
        label = _normalize_label(raw_label, caption)
        if label is None:
            continue
        normalized.append({"index": caption_index, "label": label})
        seen_indexes.add(caption_index)
    return {"labels": normalized}


def _normalize_label(raw_label: dict[str, Any], caption: dict[str, Any]) -> dict[str, Any] | None:
    normalized: dict[str, Any] = {}
    token_count = len(list(caption.get("tokens") or []))
    highlights: list[dict[str, Any]] = []
    seen_ranges: set[tuple[int, int]] = set()
    raw_highlights = raw_label.get("highlights")
    if token_count > 0 and isinstance(raw_highlights, list):
        for index, raw_highlight in enumerate(raw_highlights[:_MAX_HIGHLIGHTS]):
            if not isinstance(raw_highlight, dict):
                continue
            start_token = _coerce_int(raw_highlight.get("startToken"))
            end_token = _coerce_int(raw_highlight.get("endToken"))
            if start_token is None or end_token is None:
                continue
            if start_token < 0 or end_token <= start_token or end_token > token_count:
                continue
            highlight_text = "".join(
                str(token.get("text") or "")
                for token in list(caption.get("tokens") or [])[start_token:end_token]
            ).strip()
            normalized_highlight = {
                "startToken": start_token,
                "endToken": end_token,
                "text": highlight_text,
                "color": _DEFAULT_HIGHLIGHT_COLORS[index % len(_DEFAULT_HIGHLIGHT_COLORS)],
                "fontScale": _DEFAULT_HIGHLIGHT_SCALES[index % len(_DEFAULT_HIGHLIGHT_SCALES)],
            }
            range_key = (start_token, end_token)
            if range_key in seen_ranges:
                continue
            highlights.append(normalized_highlight)
            seen_ranges.add(range_key)
    if highlights:
        normalized["highlights"] = highlights

    return normalized or None


def _has_caption_tokens(caption: dict[str, Any]) -> bool:
    tokens = caption.get("tokens")
    return isinstance(tokens, list) and any(str(token.get("text") or "").strip() for token in tokens if isinstance(token, dict))


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
