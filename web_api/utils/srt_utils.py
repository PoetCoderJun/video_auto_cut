from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import srt

from ..constants import REMOVE_TOKEN


def _is_remove_text(text: str) -> bool:
    value = (text or "").strip()
    return not value or value.startswith(REMOVE_TOKEN)


def _strip_remove_token(text: str) -> str:
    value = (text or "").strip()
    if not value.startswith(REMOVE_TOKEN):
        return value
    value = value[len(REMOVE_TOKEN) :].strip()
    return value


def build_step1_lines_from_srt(source_srt: Path, encoding: str) -> list[dict[str, Any]]:
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


def write_final_step1_srt(lines: list[dict[str, Any]], output_path: Path, encoding: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subtitles: list[srt.Subtitle] = []

    for line in sorted(lines, key=lambda item: item["line_id"]):
        line_id = int(line["line_id"])
        start = float(line["start"])
        end = float(line["end"])
        if end <= start:
            continue

        original_text = str(line.get("original_text", "")).strip()
        optimized_text = str(line.get("optimized_text", "")).strip() or original_text
        if bool(line.get("user_final_remove", False)):
            content = f"{REMOVE_TOKEN} {original_text}".strip()
        else:
            content = optimized_text

        subtitles.append(
            srt.Subtitle(
                index=line_id,
                start=datetime.timedelta(seconds=start),
                end=datetime.timedelta(seconds=end),
                content=content,
            )
        )

    output_path.write_text(srt.compose(subtitles, reindex=False), encoding=encoding)


def write_step1_json(lines: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_topics_json(chapters: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"topics": chapters}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
