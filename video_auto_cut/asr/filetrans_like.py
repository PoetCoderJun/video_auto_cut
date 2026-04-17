from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from typing import Any


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
    raw_payload: dict[str, Any] | None = None

def segments_to_tokens(segments: list[FiletransSegment]) -> list[dict]:
    return [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]
