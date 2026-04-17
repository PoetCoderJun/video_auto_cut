from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_TEST_RUNNING,
)
from video_auto_cut.shared.test_text_io import write_chapters_text
@dataclass(frozen=True)
class LegacyStep2MigrationResult:
    jobs_scanned: int
    jobs_migrated: int


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _move_if_missing(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source.unlink(missing_ok=True)
        return False
    shutil.move(str(source), str(target))
    return True


def _convert_topics_json_to_text(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source.unlink(missing_ok=True)
        return False
    payload = _read_json(source)
    topics = payload.get("topics") if isinstance(payload, dict) else None
    if not isinstance(topics, list):
        raise RuntimeError(f"invalid topics payload: {source}")
    normalized = [dict(topic) for topic in topics if isinstance(topic, dict)]
    write_chapters_text(normalized, target)
    source.unlink(missing_ok=True)
    return True


def _target_status(raw_status: str, *, has_confirmed_output: bool, has_chapter_draft: bool) -> str | None:
    normalized = (raw_status or "").strip().upper()
    if normalized == "STEP2_CONFIRMED" or has_confirmed_output:
        return JOB_STATUS_TEST_CONFIRMED
    if normalized == "STEP2_READY" or has_chapter_draft:
        return JOB_STATUS_TEST_READY
    if normalized == "STEP2_RUNNING":
        return JOB_STATUS_TEST_RUNNING
    return None


def migrate_legacy_step2_jobs(jobs_root: Path) -> LegacyStep2MigrationResult:
    jobs_root = Path(jobs_root).expanduser().resolve()
    if not jobs_root.exists():
        return LegacyStep2MigrationResult(jobs_scanned=0, jobs_migrated=0)

    jobs_scanned = 0
    jobs_migrated = 0
    for job_dir in sorted(path for path in jobs_root.iterdir() if path.is_dir()):
        jobs_scanned += 1
        meta_path = job_dir / "job.meta.json"
        files_path = job_dir / "job.files.json"
        step2_dir = job_dir / "step2"
        test_dir = job_dir / "test"
        if not meta_path.exists():
            continue

        meta = _read_json(meta_path)
        files = _read_json(files_path)

        moved = False
        test_dir.mkdir(parents=True, exist_ok=True)
        moved |= _convert_topics_json_to_text(step2_dir / "topics.json", test_dir / "chapters_draft.txt")
        moved |= _convert_topics_json_to_text(step2_dir / "final_topics.json", test_dir / "final_chapters.txt")
        if (step2_dir / ".confirmed").exists():
            test_dir.mkdir(parents=True, exist_ok=True)
            (test_dir / ".confirmed").touch()
            (step2_dir / ".confirmed").unlink(missing_ok=True)
            moved = True

        if "topics_path" in files and "chapters_draft_path" not in files:
            files["chapters_draft_path"] = str(test_dir / "chapters_draft.txt")
            files.pop("topics_path", None)
            moved = True
        else:
            files.pop("topics_path", None)
        if "final_topics_path" in files and "final_chapters_path" not in files:
            files["final_chapters_path"] = str(test_dir / "final_chapters.txt")
            files.pop("final_topics_path", None)
            moved = True
        else:
            files.pop("final_topics_path", None)

        has_confirmed_output = (
            (test_dir / ".confirmed").exists()
            or (test_dir / "final_chapters.txt").exists()
            or (step2_dir / "final_topics.json").exists()
        )
        has_chapter_draft = (
            (test_dir / "chapters_draft.txt").exists()
            or (step2_dir / "topics.json").exists()
        )
        target_status = _target_status(
            str(meta.get("status") or ""),
            has_confirmed_output=has_confirmed_output,
            has_chapter_draft=has_chapter_draft,
        )
        if target_status is not None and str(meta.get("status") or "") != target_status:
            meta["status"] = target_status
            moved = True

        if moved:
            _write_json(meta_path, meta)
            _write_json(files_path, files)
            if step2_dir.exists() and not any(step2_dir.iterdir()):
                step2_dir.rmdir()
            jobs_migrated += 1

    return LegacyStep2MigrationResult(jobs_scanned=jobs_scanned, jobs_migrated=jobs_migrated)
