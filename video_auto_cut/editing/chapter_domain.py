from __future__ import annotations

import json
from typing import Any


def kept_test_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [dict(item) for item in lines if not bool(item.get("user_final_remove", False))]
    kept.sort(key=lambda item: int(item["line_id"]))
    return kept


def original_test_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(item) for item in lines]
    ordered.sort(key=lambda item: int(item["line_id"]))
    return ordered


def parse_block_range(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        normalized = int(value)
        if normalized < 1:
            return None
        return normalized, normalized
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if "-" not in raw:
        try:
            normalized = int(raw)
        except ValueError:
            return None
        if normalized < 1:
            return None
        return normalized, normalized

    start_raw, end_raw = raw.split("-", 1)
    try:
        start_id = int(start_raw.strip())
        end_id = int(end_raw.strip())
    except ValueError:
        return None
    if start_id < 1 or end_id < start_id:
        return None
    return start_id, end_id


def format_block_range(start_id: int, end_id: int) -> str:
    return str(start_id) if start_id == end_id else f"{start_id}-{end_id}"


def make_default_chapter_key(index: int) -> str:
    return f"chapter-{int(index):04d}"


def canonical_chapter_payload(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters, start=1):
        chapter_key = str(chapter.get("chapter_key") or "").strip() or make_default_chapter_key(index)
        raw_start = chapter.get("start_line_id")
        if raw_start is None:
            block_range = str(chapter.get("block_range") or "").strip()
            payload.append(
                {
                    "chapter_key": chapter_key,
                    "title": str(chapter.get("title") or "").strip() or f"章节{index}",
                    "block_range": block_range,
                }
            )
            continue
        payload.append(
            {
                "chapter_key": chapter_key,
                "title": str(chapter.get("title") or "").strip() or f"章节{index}",
                "start_line_id": int(raw_start),
            }
        )
    return payload


def build_document_revision(
    lines: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
) -> str:
    ordered_lines = original_test_lines(lines)
    revision_lines = [
        {
            "line_id": int(item["line_id"]),
            "start": float(item.get("start") or 0.0),
            "end": float(item.get("end") or 0.0),
            "original_text": str(item.get("original_text") or ""),
            "optimized_text": str(item.get("optimized_text") or ""),
            "ai_suggest_remove": bool(item.get("ai_suggest_remove", False)),
            "user_final_remove": bool(item.get("user_final_remove", False)),
        }
        for item in ordered_lines
    ]
    revision_chapters = canonical_chapter_payload(chapters)
    revision_chapters.sort(key=lambda item: (int(item.get("start_line_id") or 0), str(item.get("chapter_key") or "")))
    payload = {"lines": revision_lines, "chapters": revision_chapters}
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ensure_full_block_coverage(chapters: list[dict[str, Any]], total_blocks: int) -> None:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")
    if total_blocks < 1:
        raise RuntimeError("kept test lines missing")

    cursor = 1
    for idx, chapter in enumerate(chapters, start=1):
        parsed = parse_block_range(chapter.get("block_range"))
        if parsed is None:
            raise RuntimeError(f"chapter block_range invalid: {idx}")
        start_id, end_id = parsed
        if start_id != cursor:
            raise RuntimeError(f"chapter block_range not contiguous: {idx}")
        cursor = end_id + 1

    if cursor - 1 != total_blocks:
        raise RuntimeError("chapter block_range does not fully cover kept subtitles")


def _normalize_original_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = original_test_lines(lines)
    if not normalized:
        raise RuntimeError("test lines missing")
    seen: set[int] = set()
    for item in normalized:
        line_id = int(item["line_id"])
        if line_id in seen:
            raise RuntimeError(f"duplicate test line_id: {line_id}")
        seen.add(line_id)
    return normalized


def _legacy_chapters_to_start_anchors(
    chapters: list[dict[str, Any]],
    all_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept_lines = kept_test_lines(all_lines)
    if not kept_lines:
        raise RuntimeError("kept test lines missing")
    ensure_full_block_coverage(chapters, total_blocks=len(kept_lines))
    first_original_line_id = int(_normalize_original_lines(all_lines)[0]["line_id"])
    normalized: list[dict[str, Any]] = []
    for idx, chapter in enumerate(chapters, start=1):
        parsed = parse_block_range(chapter.get("block_range"))
        if parsed is None:
            raise RuntimeError(f"chapter block_range invalid: {idx}")
        start_idx, end_idx = parsed
        if end_idx > len(kept_lines):
            raise RuntimeError(f"chapter block_range out of bounds: {idx}")
        chosen = kept_lines[start_idx - 1 : end_idx]
        if not chosen:
            raise RuntimeError(f"chapter block_range empty: {idx}")
        normalized.append(
            {
                "chapter_key": str(chapter.get("chapter_key") or "").strip() or make_default_chapter_key(idx),
                "title": str(chapter.get("title") or "").strip() or f"章节{idx}",
                "start_line_id": first_original_line_id if idx == 1 else int(chosen[0]["line_id"]),
            }
        )
    return normalized


def _canonical_chapter_starts(
    chapters: list[dict[str, Any]],
    all_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")

    normalized_lines = _normalize_original_lines(all_lines)
    available_line_ids = {int(item["line_id"]) for item in normalized_lines}
    first_line_id = int(normalized_lines[0]["line_id"])

    if all(chapter.get("start_line_id") is not None for chapter in chapters):
        normalized: list[dict[str, Any]] = []
        for idx, chapter in enumerate(chapters, start=1):
            if chapter.get("start_line_id") is None:
                raise RuntimeError(f"chapter start_line_id missing: {idx}")
            start_line_id = int(chapter.get("start_line_id") or 0)
            if start_line_id not in available_line_ids:
                raise RuntimeError(f"chapter start_line_id invalid: {idx}")
            normalized.append(
                {
                    "chapter_key": str(chapter.get("chapter_key") or "").strip() or make_default_chapter_key(idx),
                    "title": str(chapter.get("title") or "").strip() or f"章节{idx}",
                    "start_line_id": start_line_id,
                }
            )
    else:
        normalized = _legacy_chapters_to_start_anchors(chapters, normalized_lines)

    normalized.sort(key=lambda item: int(item["start_line_id"]))
    if int(normalized[0]["start_line_id"]) != first_line_id:
        raise RuntimeError("first chapter must start at the first line")

    seen_keys: set[str] = set()
    seen_starts: set[int] = set()
    for idx, chapter in enumerate(normalized, start=1):
        chapter_key = str(chapter["chapter_key"])
        start_line_id = int(chapter["start_line_id"])
        if chapter_key in seen_keys:
            raise RuntimeError(f"duplicate chapter_key: {chapter_key}")
        if start_line_id in seen_starts:
            raise RuntimeError(f"duplicate chapter start_line_id: {start_line_id}")
        seen_keys.add(chapter_key)
        seen_starts.add(start_line_id)
        chapter["chapter_id"] = idx
    return normalized


def canonicalize_test_chapters(
    chapters: list[dict[str, Any]],
    all_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_lines = _normalize_original_lines(all_lines)
    canonical = _canonical_chapter_starts(chapters, normalized_lines)
    line_index = {int(item["line_id"]): index for index, item in enumerate(normalized_lines)}
    kept_lines = kept_test_lines(normalized_lines)
    kept_positions = {int(item["line_id"]): index + 1 for index, item in enumerate(kept_lines)}

    materialized: list[dict[str, Any]] = []
    for index, chapter in enumerate(canonical):
        start_line_id = int(chapter["start_line_id"])
        start_index = line_index[start_line_id]
        next_start_line_id = (
            int(canonical[index + 1]["start_line_id"]) if index + 1 < len(canonical) else None
        )
        end_index = (
            line_index[next_start_line_id] - 1
            if next_start_line_id is not None
            else len(normalized_lines) - 1
        )
        chapter_lines = normalized_lines[start_index : end_index + 1]
        active_lines = [
            dict(item) for item in chapter_lines if not bool(item.get("user_final_remove", False))
        ]
        active_start_line_id = int(active_lines[0]["line_id"]) if active_lines else None
        active_end_line_id = int(active_lines[-1]["line_id"]) if active_lines else None
        block_range = ""
        if active_lines:
            block_range = format_block_range(
                kept_positions[int(active_lines[0]["line_id"])],
                kept_positions[int(active_lines[-1]["line_id"])],
            )
        materialized.append(
            {
                "chapter_key": str(chapter["chapter_key"]),
                "chapter_id": index + 1,
                "title": str(chapter.get("title") or "").strip() or f"章节{index + 1}",
                "start_line_id": start_line_id,
                "end_line_id": int(chapter_lines[-1]["line_id"]),
                "active_start_line_id": active_start_line_id,
                "active_end_line_id": active_end_line_id,
                "start": float(active_lines[0]["start"]) if active_lines else None,
                "end": float(active_lines[-1]["end"]) if active_lines else None,
                "active_line_count": len(active_lines),
                "block_range": block_range,
            }
        )
    return materialized


def validate_non_empty_chapters(chapters: list[dict[str, Any]]) -> None:
    empty = [
        str(item.get("title") or f"章节{idx}").strip() or f"章节{idx}"
        for idx, item in enumerate(chapters, start=1)
        if int(item.get("active_line_count") or 0) <= 0
    ]
    if empty:
        joined = " / ".join(empty)
        raise RuntimeError(f"empty chapters require cleanup before confirm: {joined}")
