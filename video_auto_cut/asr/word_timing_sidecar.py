from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sidecar_path_for_srt(srt_path: Path | str) -> Path:
    path = Path(srt_path)
    return path.with_suffix(".asr.words.json")


def build_sidecar_from_dashscope_payload(
    payload: dict[str, Any],
    *,
    asset_id: str,
    upstream_task_id: str | None = None,
) -> dict[str, Any] | None:
    transcripts = payload.get("transcripts")
    if not isinstance(transcripts, list) or not transcripts:
        return None

    words: list[dict[str, Any]] = []
    sentences: list[dict[str, Any]] = []
    global_word_index = 0
    language: str | None = None

    for transcript in transcripts:
        if not isinstance(transcript, dict):
            continue
        transcript_language = _normalize_language(transcript.get("language"))
        rows = transcript.get("sentences")
        if not isinstance(rows, list):
            continue
        for sentence_position, sentence in enumerate(rows):
            if not isinstance(sentence, dict):
                continue
            raw_words = sentence.get("words")
            if not isinstance(raw_words, list) or not raw_words:
                continue
            normalized_words = _normalize_sentence_words(raw_words, start_index=global_word_index)
            if not normalized_words:
                continue
            if language is None:
                language = _normalize_language(sentence.get("language")) or transcript_language
            sentence_text = str(sentence.get("text") or "").strip() or "".join(
                f"{item['text']}{item['punct']}" for item in normalized_words
            )
            sentences.append(
                {
                    "sentence_id": _to_int(sentence.get("sentence_id"), default=len(sentences)),
                    "order": len(sentences),
                    "text": sentence_text,
                    "start_ms": normalized_words[0]["start_ms"],
                    "end_ms": max(item["end_ms"] for item in normalized_words),
                    "word_start_index": normalized_words[0]["index"],
                    "word_end_index": normalized_words[-1]["index"],
                    "source_sentence_index": sentence_position,
                }
            )
            words.extend(normalized_words)
            global_word_index += len(normalized_words)

    if not words:
        return None

    audio_info = payload.get("audio_info") if isinstance(payload.get("audio_info"), dict) else {}
    return {
        "version": 1,
        "source": "dashscope",
        "asset_id": str(asset_id or "").strip(),
        "language": language or "unknown",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "audio": {
            "duration_ms": _to_int(
                audio_info.get("duration_ms")
                or audio_info.get("duration")
                or audio_info.get("duration_milliseconds"),
                default=None,
            )
        },
        "words": words,
        "sentences": sentences,
        "meta": {
            "upstream_task_id": str(upstream_task_id or "").strip() or None,
            "schema_note": "raw word timings sidecar",
        },
    }


def write_sidecar(path: Path | str, payload: dict[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_sidecar(path: Path | str) -> dict[str, Any] | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    words = payload.get("words")
    if not isinstance(words, list) or not words:
        return None
    payload["words"] = [item for item in words if _is_valid_word_entry(item)]
    if not payload["words"]:
        return None
    return payload


def _normalize_sentence_words(raw_words: list[dict[str, Any]], *, start_index: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for offset, raw in enumerate(raw_words):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "")
        punct = str(raw.get("punctuation") or "")
        if not text and not punct:
            continue
        start_ms = _to_int(raw.get("begin_time"), default=None)
        end_ms = _to_int(raw.get("end_time"), default=None)
        if start_ms is None or end_ms is None:
            continue
        if start_ms < 0:
            start_ms = 0
        if end_ms < start_ms:
            continue
        normalized.append(
            {
                "index": start_index + len(normalized),
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker": raw.get("speaker"),
                "confidence": raw.get("confidence"),
                "punct": punct,
            }
        )
    return normalized


def _is_valid_word_entry(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    text = str(item.get("text") or "")
    punct = str(item.get("punct") or "")
    if not text and not punct:
        return False
    start_ms = _to_int(item.get("start_ms"), default=None)
    end_ms = _to_int(item.get("end_ms"), default=None)
    return start_ms is not None and end_ms is not None and start_ms >= 0 and end_ms >= start_ms


def _normalize_language(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_int(value: Any, *, default: int | None) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized
