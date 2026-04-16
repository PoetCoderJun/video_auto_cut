from typing import Dict, List, Optional, Tuple

import srt

REMOVE_TOKEN = "<remove>"


def parse_decision_and_text(content: str) -> Tuple[Optional[str], str]:
    text = "\n".join(line.strip() for line in (content or "").splitlines() if line.strip()).strip()
    return None, text


def filter_kept_subtitles(subs: List[srt.Subtitle]) -> List[srt.Subtitle]:
    kept: List[srt.Subtitle] = []
    for sub in subs:
        _, text = parse_decision_and_text(sub.content or "")
        if text.startswith(REMOVE_TOKEN):
            continue
        if not text or sub.end <= sub.start:
            continue

        kept.append(
            srt.Subtitle(
                index=sub.index,
                start=sub.start,
                end=sub.end,
                content=text,
            )
        )

    kept.sort(key=lambda x: x.start)
    return kept


def build_merged_segments(
    subs: List[srt.Subtitle], merge_gap_s: float = 0.5
) -> List[Dict[str, float]]:
    segments: List[Dict[str, float]] = []
    for sub in subs:
        start = max(0.0, sub.start.total_seconds())
        end = max(start, sub.end.total_seconds())
        if end <= start:
            continue

        if not segments:
            segments.append({"start": start, "end": end})
            continue

        if start - segments[-1]["end"] < merge_gap_s:
            segments[-1]["end"] = max(segments[-1]["end"], end)
        else:
            segments.append({"start": start, "end": end})
    return segments
