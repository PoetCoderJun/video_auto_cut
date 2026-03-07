from __future__ import annotations

from typing import Any

from .pi_agent_models import ChunkWindow

DEFAULT_CHUNK_LINES = 30
DEFAULT_OVERLAP_LINES = 4


def build_chunk_windows(
    segments: list[dict[str, Any]],
    chunk_lines: int = DEFAULT_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> list[ChunkWindow]:
    if not segments:
        return []

    total = len(segments)
    windows: list[ChunkWindow] = []

    for chunk_id, start in enumerate(range(0, total, chunk_lines), start=1):
        end = min(start + chunk_lines, total)
        left_overlap = min(overlap_lines, start)
        right_overlap = min(overlap_lines, total - end)
        context_start = start - left_overlap
        context_end = end + right_overlap
        windows.append(
            ChunkWindow(
                chunk_id=chunk_id,
                context_start=context_start + 1,
                context_end=context_end,
                core_start=start + 1,
                core_end=end,
                left_overlap=left_overlap,
                right_overlap=right_overlap,
            )
        )

    return windows
