from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .line_contract import TestLine, build_test_line, normalize_test_lines


EditLine = TestLine


@dataclass(frozen=True)
class EditDocument:
    lines: list[EditLine]

    @classmethod
    def from_lines(cls, lines: list[dict[str, Any]]) -> "EditDocument":
        return cls(lines=list(normalize_test_lines(lines)))

    @classmethod
    def from_segments(cls, segments: list[dict[str, Any]]) -> "EditDocument":
        return cls(
            lines=[
                build_test_line(
                    line_id=int(segment.get("id") or index),
                    start=float(segment.get("start") or 0.0),
                    end=float(segment.get("end") or 0.0),
                    original_text=str(segment.get("text") or "").strip(),
                )
                for index, segment in enumerate(segments, start=1)
                if isinstance(segment, dict)
            ]
        )

    def kept_lines(self) -> list[EditLine]:
        return [line for line in self.lines if not bool(line.get("user_final_remove", False))]
