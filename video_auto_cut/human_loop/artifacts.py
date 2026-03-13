from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import srt

REMOVE_TOKEN = "<<REMOVE>>"

STATUS_CREATED = "CREATED"
STATUS_STEP1_READY = "STEP1_READY"
STATUS_STEP1_CONFIRMED = "STEP1_CONFIRMED"
STATUS_STEP2_READY = "STEP2_READY"
STATUS_STEP2_CONFIRMED = "STEP2_CONFIRMED"
STATUS_SUCCEEDED = "SUCCEEDED"


@dataclass(frozen=True)
class HumanLoopPaths:
    artifact_root: Path
    state_json: Path
    input_dir: Path
    step1_dir: Path
    step2_dir: Path
    render_dir: Path
    staged_video_path: Path
    step1_source_srt: Path
    step1_optimized_srt: Path
    step1_sidecar_json: Path
    step1_draft_srt: Path
    step1_draft_json: Path
    step1_final_srt: Path
    step1_final_json: Path
    step2_cut_srt: Path
    step2_topics_json: Path
    step2_draft_json: Path
    step2_final_json: Path
    render_cut_srt: Path
    render_output_path: Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_artifact_root(input_video_path: Path, artifact_root: str | None = None) -> Path:
    if artifact_root:
        return Path(artifact_root).expanduser().resolve()
    return (input_video_path.parent / f"{input_video_path.stem}.video-auto-cut").resolve()


def ensure_paths(input_video_path: Path, artifact_root: str | None = None) -> HumanLoopPaths:
    resolved_root = derive_artifact_root(input_video_path, artifact_root)
    input_dir = resolved_root / "input"
    step1_dir = resolved_root / "step1"
    step2_dir = resolved_root / "step2"
    render_dir = resolved_root / "render"
    for path in (resolved_root, input_dir, step1_dir, step2_dir, render_dir):
        path.mkdir(parents=True, exist_ok=True)

    staged_video_path = input_dir / f"source{input_video_path.suffix.lower()}"
    return HumanLoopPaths(
        artifact_root=resolved_root,
        state_json=resolved_root / "state.json",
        input_dir=input_dir,
        step1_dir=step1_dir,
        step2_dir=step2_dir,
        render_dir=render_dir,
        staged_video_path=staged_video_path,
        step1_source_srt=step1_dir / "source.srt",
        step1_optimized_srt=step1_dir / "source.optimized.srt",
        step1_sidecar_json=step1_dir / "source.optimized.step1.json",
        step1_draft_srt=step1_dir / "draft_step1.srt",
        step1_draft_json=step1_dir / "draft_step1.json",
        step1_final_srt=step1_dir / "final_step1.srt",
        step1_final_json=step1_dir / "final_step1.json",
        step2_cut_srt=step2_dir / "cut.srt",
        step2_topics_json=step2_dir / "topics.json",
        step2_draft_json=step2_dir / "draft_topics.json",
        step2_final_json=step2_dir / "final_topics.json",
        render_cut_srt=render_dir / "cut.srt",
        render_output_path=render_dir / "output.mp4",
    )


def load_state(paths: HumanLoopPaths) -> dict[str, Any]:
    if not paths.state_json.exists():
        return {}
    try:
        payload = json.loads(paths.state_json.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(paths: HumanLoopPaths, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["artifact_root"] = str(paths.artifact_root)
    payload["updated_at"] = now_iso()
    if not payload.get("created_at"):
        payload["created_at"] = payload["updated_at"]
    tmp_path = paths.state_json.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(paths.state_json)
    return payload


def initialize_state(
    paths: HumanLoopPaths,
    *,
    input_video_path: Path,
    output_video_path: Path,
) -> dict[str, Any]:
    existing = load_state(paths)
    payload = {
        "schema_version": 1,
        "status": existing.get("status") or STATUS_CREATED,
        "input_video_path": str(input_video_path),
        "output_video_path": str(output_video_path),
        "staged_video_path": str(existing.get("staged_video_path") or paths.staged_video_path),
        "step1_confirmed": bool(existing.get("step1_confirmed", False)),
        "step2_confirmed": bool(existing.get("step2_confirmed", False)),
        "created_at": existing.get("created_at") or now_iso(),
    }
    return save_state(paths, payload)


def stage_input_video(input_video_path: Path, paths: HumanLoopPaths) -> Path:
    staged = paths.staged_video_path
    if staged.exists() or staged.is_symlink():
        return staged
    try:
        os.symlink(str(input_video_path), str(staged))
    except OSError:
        shutil.copy2(input_video_path, staged)
    return staged


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def read_step1_lines(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    lines = payload.get("lines") if isinstance(payload, dict) else payload
    if not isinstance(lines, list):
        raise RuntimeError(f"invalid step1 payload: {path}")

    normalized: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        normalized.append(
            {
                "line_id": int(line["line_id"]),
                "start": float(line["start"]),
                "end": float(line["end"]),
                "original_text": str(line.get("original_text", "")).strip(),
                "optimized_text": str(line.get("optimized_text", "")).strip(),
                "ai_suggest_remove": bool(line.get("ai_suggest_remove", False)),
                "user_final_remove": bool(line.get("user_final_remove", False)),
            }
        )
    normalized.sort(key=lambda item: int(item["line_id"]))
    return normalized


def write_step1_json(lines: list[dict[str, Any]], path: Path) -> None:
    _write_json(path, {"lines": lines})


def write_step1_srt(lines: list[dict[str, Any]], path: Path, encoding: str) -> None:
    subtitles: list[srt.Subtitle] = []
    for line in sorted(lines, key=lambda item: int(item["line_id"])):
        start = float(line.get("start", 0.0))
        end = float(line.get("end", 0.0))
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
                index=int(line["line_id"]),
                start=timedelta(seconds=start),
                end=timedelta(seconds=end),
                content=content,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(srt.compose(subtitles, reindex=False), encoding=encoding)


def kept_line_ids(lines: list[dict[str, Any]]) -> list[int]:
    result = [
        int(line["line_id"])
        for line in lines
        if not bool(line.get("user_final_remove", False))
    ]
    result.sort()
    return result


def read_topics(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    topics = payload.get("topics") if isinstance(payload, dict) else payload
    if not isinstance(topics, list):
        raise RuntimeError(f"invalid topics payload: {path}")

    normalized: list[dict[str, Any]] = []
    for idx, chapter in enumerate(topics, start=1):
        if not isinstance(chapter, dict):
            continue
        start = float(chapter.get("start", 0.0))
        end = float(chapter.get("end", 0.0))
        if end <= start:
            continue
        raw_line_ids = chapter.get("line_ids")
        if not isinstance(raw_line_ids, list):
            raw_line_ids = chapter.get("segment_ids") if isinstance(chapter.get("segment_ids"), list) else []
        normalized.append(
            {
                "chapter_id": int(chapter.get("chapter_id", idx)),
                "title": str(chapter.get("title") or f"章节{idx}").strip() or f"章节{idx}",
                "start": start,
                "end": end,
                "line_ids": [int(item) for item in raw_line_ids if isinstance(item, (int, float))],
            }
        )
    normalized.sort(key=lambda item: int(item["chapter_id"]))
    return normalized


def write_topics_json(chapters: list[dict[str, Any]], path: Path) -> None:
    _write_json(path, {"topics": chapters})


def map_line_ids_to_step1(raw_line_ids: list[int], kept_ids: list[int]) -> list[int]:
    if not raw_line_ids:
        return []
    kept_set = set(kept_ids)
    seen: set[int] = set()
    mapped: list[int] = []
    total = len(kept_ids)
    for raw in raw_line_ids:
        candidate: int | None = None
        if raw in kept_set:
            candidate = raw
        elif 1 <= raw <= total:
            candidate = kept_ids[raw - 1]
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        mapped.append(candidate)
    return mapped


def ensure_full_line_coverage(chapters: list[dict[str, Any]], kept_ids: list[int]) -> list[dict[str, Any]]:
    kept_set = set(kept_ids)
    for chapter in chapters:
        chapter["line_ids"] = map_line_ids_to_step1(list(chapter.get("line_ids") or []), kept_ids)

    assigned = {
        lid
        for chapter in chapters
        for lid in chapter.get("line_ids", [])
        if lid in kept_set
    }
    missing = [lid for lid in kept_ids if lid not in assigned]
    for lid in missing:
        target_idx = len(chapters) - 1
        for idx, chapter in enumerate(chapters):
            ids = chapter.get("line_ids") or []
            if ids and lid <= max(ids):
                target_idx = idx
                break
        chapters[target_idx]["line_ids"].append(lid)

    for chapter in chapters:
        deduped = sorted(
            set(int(item) for item in chapter.get("line_ids", []) if int(item) in kept_set)
        )
        chapter["line_ids"] = deduped
    return chapters
