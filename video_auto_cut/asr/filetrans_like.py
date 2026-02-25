from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


TaskStatus = Literal["RUNNING", "SUCCEEDED", "FAILED"]


@dataclass(frozen=True)
class FiletransSubmitResponse:
    task_id: str


@dataclass(frozen=True)
class FiletransTask:
    task_id: str
    task_status: TaskStatus
    transcription_url: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class FiletransSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class FiletransResult:
    task_id: str
    segments: list[FiletransSegment]


def _new_task_id() -> str:
    return f"local_{uuid.uuid4().hex[:18]}"


def _now_ms() -> int:
    return int(time.time() * 1000)


class LocalFiletransLikeASR:
    """
    A local adapter that mimics the minimal Filetrans workflow:
    - submit(...) returns task_id
    - poll(...) returns SUCCEEDED and a transcription_url (a local json path)
    - load_result(...) reads the json and returns segments

    This lets the rest of the pipeline integrate with a future cloud Filetrans client
    with minimal changes.
    """

    def __init__(self, *, result_dir: Path):
        self._result_dir = Path(result_dir)
        self._result_dir.mkdir(parents=True, exist_ok=True)

    def submit(
        self,
        *,
        media_path: Path,
        transcribe_fn,
        lang: str | None,
        prompt: str,
    ) -> FiletransSubmitResponse:
        task_id = _new_task_id()
        result_path = self._result_path(task_id)

        # Run locally and persist a Filetrans-like result json.
        tokens = transcribe_fn(media_path=media_path, lang=lang, prompt=prompt)
        segments = [
            {"start": float(item["start"]), "end": float(item["end"]), "text": str(item["text"])}
            for item in (tokens or [])
            if isinstance(item, dict) and "start" in item and "end" in item and "text" in item
        ]
        payload = {
            "task_id": task_id,
            "task_status": "SUCCEEDED",
            "created_at_ms": _now_ms(),
            "segments": segments,
        }
        tmp = result_path.with_suffix(result_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(result_path)
        return FiletransSubmitResponse(task_id=task_id)

    def poll(self, task_id: str) -> FiletransTask:
        result_path = self._result_path(task_id)
        if not result_path.exists():
            return FiletransTask(task_id=task_id, task_status="RUNNING")
        return FiletransTask(
            task_id=task_id,
            task_status="SUCCEEDED",
            transcription_url=str(result_path),
        )

    def load_result(self, transcription_url: str) -> FiletransResult:
        path = Path(transcription_url).expanduser()
        payload = json.loads(path.read_text(encoding="utf-8"))
        task_id = str(payload.get("task_id") or "")
        raw_segments = payload.get("segments") or []
        segments: list[FiletransSegment] = []
        if isinstance(raw_segments, list):
            for item in raw_segments:
                if not isinstance(item, dict):
                    continue
                try:
                    start = float(item["start"])
                    end = float(item["end"])
                    text = str(item["text"])
                except Exception:
                    continue
                if end <= start or not text.strip():
                    continue
                segments.append(FiletransSegment(start=start, end=end, text=text.strip()))
        return FiletransResult(task_id=task_id, segments=segments)

    def _result_path(self, task_id: str) -> Path:
        safe = "".join(ch for ch in task_id if ch.isalnum() or ch in ("_", "-"))
        safe = safe or "task"
        return self._result_dir / f"{safe}.transcription.json"


def segments_to_tokens(segments: list[FiletransSegment]) -> list[dict]:
    return [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]

