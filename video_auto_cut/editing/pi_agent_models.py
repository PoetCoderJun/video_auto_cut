from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


RemoveAction = Literal["KEEP", "REMOVE"]


@dataclass(frozen=True)
class ChunkWindow:
    chunk_id: int
    context_start: int
    context_end: int
    core_start: int
    core_end: int
    left_overlap: int
    right_overlap: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class LineDecision:
    line_id: int
    original_text: str
    current_text: str
    remove_action: RemoveAction
    reason: str
    confidence: float
    source_line_ids: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.source_line_ids:
            object.__setattr__(self, "source_line_ids", [self.line_id])

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MergedGroup:
    source_line_ids: list[int]
    text: str
    start: float
    end: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ChunkExecutionState:
    window: ChunkWindow
    decisions: list[LineDecision]
    merged_groups: list[MergedGroup]
    core_line_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "window": self.window.to_dict(),
            "decisions": [decision.to_dict() for decision in self.decisions],
            "merged_groups": [group.to_dict() for group in self.merged_groups],
            "core_line_ids": list(self.core_line_ids),
        }


@dataclass(frozen=True)
class BoundaryReviewState:
    previous_chunk_id: int
    current_chunk_id: int
    dropped_line_ids: list[int]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
