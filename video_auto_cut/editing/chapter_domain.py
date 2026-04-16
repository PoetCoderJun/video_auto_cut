from __future__ import annotations

import json
from typing import Any

def kept_test_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [dict(item) for item in lines if not bool(item.get("user_final_remove", False))]
    kept.sort(key=lambda item: int(item["line_id"]))
    return kept


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


def build_document_revision(
    lines: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
) -> str:
    payload = {"lines": lines, "chapters": chapters}
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


def canonicalize_test_chapters(
    chapters: list[dict[str, Any]],
    kept_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not chapters:
        raise RuntimeError("chapters cannot be empty")
    canonical_kept_lines = kept_test_lines(kept_lines)
    if not canonical_kept_lines:
        raise RuntimeError("kept test lines missing")

    normalized: list[dict[str, Any]] = []
    for idx, chapter in enumerate(chapters, start=1):
        parsed = parse_block_range(chapter.get("block_range"))
        if parsed is None:
            raise RuntimeError(f"chapter block_range invalid: {idx}")
        start_idx, end_idx = parsed
        if end_idx > len(canonical_kept_lines):
            raise RuntimeError(f"chapter block_range out of bounds: {idx}")
        chosen = canonical_kept_lines[start_idx - 1 : end_idx]
        if not chosen:
            raise RuntimeError(f"chapter block_range empty: {idx}")
        normalized.append(
            {
                "chapter_id": int(chapter.get("chapter_id", idx)),
                "title": str(chapter.get("title") or "").strip() or f"章节{idx}",
                "start": float(chosen[0]["start"]),
                "end": float(chosen[-1]["end"]),
                "block_range": format_block_range(start_idx, end_idx),
            }
        )
    ensure_full_block_coverage(normalized, total_blocks=len(canonical_kept_lines))
    return normalized


canonicalize_test_chapters = canonicalize_test_chapters


def line_ids_to_block_range(
    line_ids: list[int],
    kept_lines: list[dict[str, Any]],
) -> tuple[int, int] | None:
    if not line_ids or not kept_lines:
        return None
    position_by_line_id = {
        int(item["line_id"]): index + 1 for index, item in enumerate(kept_lines)
    }
    positions = sorted(
        {
            position_by_line_id[int(line_id)]
            for line_id in line_ids
            if int(line_id) in position_by_line_id
        }
    )
    if not positions:
        return None
    return positions[0], positions[-1]
