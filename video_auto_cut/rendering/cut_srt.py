from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List

import srt

from .cut import build_merged_segments, filter_kept_subtitles


def load_kept_subtitles(srt_path: str, encoding: str) -> List[srt.Subtitle]:
    with open(srt_path, encoding=encoding) as f:
        subs = list(srt.parse(f.read()))
    return filter_kept_subtitles(subs)


def build_remapped_captions(
    kept_subs: List[srt.Subtitle], segments: List[Dict[str, float]]
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, float]] = []
    cursor = 0.0
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        timeline.append({"start": start, "end": end, "out_start": cursor})
        cursor += end - start

    captions: List[Dict[str, Any]] = []
    seg_idx = 0
    eps = 1e-4

    for sub in kept_subs:
        start = sub.start.total_seconds()
        end = sub.end.total_seconds()

        while seg_idx + 1 < len(timeline):
            seg_end = timeline[seg_idx]["end"]
            if start > seg_end + eps:
                seg_idx += 1
                continue
            if abs(start - seg_end) <= eps and end > seg_end + eps:
                seg_idx += 1
                continue
            break

        seg = timeline[seg_idx]
        if start < seg["start"] - eps or end > seg["end"] + eps:
            logging.warning(
                "Subtitle %.3f-%.3f is out of cut segment %.3f-%.3f",
                start,
                end,
                seg["start"],
                seg["end"],
            )
            continue

        out_start = seg["out_start"] + (start - seg["start"])
        out_end = seg["out_start"] + (end - seg["start"])
        if out_end <= out_start:
            continue

        captions.append(
            {
                "start": round(out_start, 3),
                "end": round(out_end, 3),
                "text": (sub.content or "").strip(),
            }
        )

    return captions


def write_cut_srt(captions: List[Dict[str, Any]], output_srt_path: str, encoding: str) -> str:
    output_path = Path(output_srt_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subs: List[srt.Subtitle] = []
    for idx, cap in enumerate(captions, start=1):
        start = float(cap.get("start") or 0.0)
        end = float(cap.get("end") or 0.0)
        if end <= start:
            continue
        text = str(cap.get("text") or "").strip()
        if not text:
            continue
        subs.append(
            srt.Subtitle(
                index=idx,
                start=datetime.timedelta(seconds=start),
                end=datetime.timedelta(seconds=end),
                content=text,
            )
        )

    with open(output_path, "wb") as f:
        f.write(srt.compose(subs, reindex=False).encode(encoding, "replace"))
    logging.info("Saved cut subtitles to %s", output_path)
    return str(output_path)


def build_cut_srt_from_optimized_srt(
    source_srt_path: str,
    output_srt_path: str,
    encoding: str,
    merge_gap_s: float,
) -> Dict[str, Any]:
    kept_subs = load_kept_subtitles(source_srt_path, encoding)
    if not kept_subs:
        raise RuntimeError("No kept subtitles found in optimized SRT.")

    segments = build_merged_segments(kept_subs, merge_gap_s=merge_gap_s)
    captions = build_remapped_captions(kept_subs, segments)
    if not captions:
        raise RuntimeError("No captions available after remapping subtitle timeline.")

    cut_srt_path = write_cut_srt(captions, output_srt_path, encoding)
    return {
        "cut_srt_path": cut_srt_path,
        "kept_subtitles": kept_subs,
        "segments": segments,
        "captions": captions,
    }
