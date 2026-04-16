from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import srt

from video_auto_cut.shared.test_text_protocol import (
    TIMED_LINE_RE,
    parse_chapter_line,
    parse_time,
    render_chapter_line,
    render_test_line_text,
)

REMOVE_TOKEN = "<remove>"
LEGACY_REMOVE_TOKEN = "<<REMOVE>>"


def _is_remove_text(text: str) -> bool:
    value = (text or "").strip()
    return not value or value.startswith(REMOVE_TOKEN) or value.startswith(LEGACY_REMOVE_TOKEN)


def _strip_remove_token(text: str) -> str:
    value = (text or "").strip()
    if value.startswith(REMOVE_TOKEN):
        return value[len(REMOVE_TOKEN) :].strip()
    if value.startswith(LEGACY_REMOVE_TOKEN):
        return value[len(LEGACY_REMOVE_TOKEN) :].strip()
    return value


def build_test_lines_from_srt(source_srt: Path, encoding: str) -> list[dict[str, Any]]:
    subtitles = list(srt.parse(source_srt.read_text(encoding=encoding)))
    lines: list[dict[str, Any]] = []
    for idx, subtitle in enumerate(subtitles, start=1):
        line_id = int(subtitle.index) if int(subtitle.index) > 0 else idx
        raw_text = (subtitle.content or "").strip()
        ai_suggest_remove = _is_remove_text(raw_text)
        text = _strip_remove_token(raw_text)
        lines.append(
            {
                "line_id": line_id,
                "start": float(subtitle.start.total_seconds()),
                "end": float(subtitle.end.total_seconds()),
                "original_text": text,
                "optimized_text": text,
                "ai_suggest_remove": ai_suggest_remove,
                "user_final_remove": ai_suggest_remove,
            }
        )
    lines.sort(key=lambda item: item["line_id"])
    return lines


def build_test_lines_from_text(source_text: Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for index, raw_line in enumerate(source_text.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = TIMED_LINE_RE.match(line)
        if not match:
            raise RuntimeError(f"invalid test text line: {line}")
        text = (match.group("text") or "").strip()
        remove = bool(match.group("remove"))
        lines.append(
            {
                "line_id": index,
                "start": float(parse_time(match.group("start"))),
                "end": float(parse_time(match.group("end"))),
                "original_text": text,
                "optimized_text": text,
                "ai_suggest_remove": remove,
                "user_final_remove": remove,
            }
        )
    return lines


def build_test_lines_from_json(source_json: Path) -> list[dict[str, Any]]:
    payload = json.loads(source_json.read_text(encoding="utf-8"))
    lines = payload.get("lines") if isinstance(payload, dict) else payload
    if not isinstance(lines, list):
        raise RuntimeError(f"invalid test lines payload: {source_json}")
    normalized = [dict(line) for line in lines if isinstance(line, dict)]
    normalized.sort(key=lambda item: int(item["line_id"]))
    return normalized


def load_test_lines(source_path: Path) -> list[dict[str, Any]]:
    if source_path.suffix.lower() == ".json":
        return build_test_lines_from_json(source_path)
    return build_test_lines_from_text(source_path)


def write_test_text(lines: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(
        render_test_line_text(
            start=float(line["start"]),
            end=float(line["end"]),
            text=str(line.get("optimized_text") or line.get("original_text") or "").strip(),
            remove=bool(line.get("user_final_remove", False)),
        )
        for line in sorted(lines, key=lambda item: int(item["line_id"]))
    )
    output_path.write_text((rendered + "\n") if rendered else "", encoding="utf-8")


def build_test_chapters_from_text(source_text: Path, *, kept_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from video_auto_cut.editing.chapter_domain import canonicalize_test_chapters

    chapters: list[dict[str, Any]] = []
    for raw_line in source_text.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        start, end, title = parse_chapter_line(line)
        chapters.append(
            {
                "chapter_id": len(chapters) + 1,
                "title": title,
                "block_range": f"{start}-{end}" if start != end else str(start),
            }
        )
    return canonicalize_test_chapters(chapters, kept_lines)


def build_test_chapters_from_json(
    source_json: Path, *, kept_lines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from video_auto_cut.editing.chapter_domain import canonicalize_test_chapters

    payload = json.loads(source_json.read_text(encoding="utf-8"))
    chapters = payload.get("topics") if isinstance(payload, dict) else payload
    if not isinstance(chapters, list):
        raise RuntimeError(f"invalid chapter payload: {source_json}")
    normalized = [dict(chapter) for chapter in chapters if isinstance(chapter, dict)]
    return canonicalize_test_chapters(normalized, kept_lines)


def load_test_chapters(
    source_path: Path, *, kept_lines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if source_path.suffix.lower() == ".json":
        return build_test_chapters_from_json(source_path, kept_lines=kept_lines)
    return build_test_chapters_from_text(source_path, kept_lines=kept_lines)


def write_final_test_srt(lines: list[dict[str, Any]], output_path: Path, encoding: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subtitles: list[srt.Subtitle] = []
    for line in sorted(lines, key=lambda item: int(item["line_id"])):
        line_id = int(line["line_id"])
        start = float(line["start"])
        end = float(line["end"])
        if end <= start:
            continue
        original_text = str(line.get("original_text", "")).strip()
        optimized_text = str(line.get("optimized_text", "")).strip() or original_text
        content = f"{REMOVE_TOKEN}{original_text}".strip() if bool(line.get("user_final_remove", False)) else optimized_text
        subtitles.append(
            srt.Subtitle(
                index=line_id,
                start=datetime.timedelta(seconds=start),
                end=datetime.timedelta(seconds=end),
                content=content,
            )
        )
    output_path.write_text(srt.compose(subtitles, reindex=False), encoding=encoding)


def write_test_json(lines: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_topics_json(chapters: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"topics": chapters}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_chapters_text(chapters: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(
        render_chapter_line(
            block_range=str(chapter.get("block_range") or "").strip(),
            title=str(chapter.get("title") or "").strip(),
        )
        for chapter in sorted(chapters, key=lambda item: int(item.get("chapter_id", 0)))
    )
    output_path.write_text((rendered + "\n") if rendered else "", encoding="utf-8")
