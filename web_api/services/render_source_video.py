from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable


def _normalize_segments(segments: Iterable[dict[str, object]]) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for segment in segments:
        try:
            start = float(segment["start"])  # type: ignore[index]
            end = float(segment["end"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        normalized.append((round(start, 3), round(end, 3)))
    return normalized


def _probe_primary_audio_stream(input_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(payload.get("streams"))


def build_cut_source_video_command(
    *,
    input_path: Path,
    output_path: Path,
    segments: Iterable[dict[str, object]],
    include_audio: bool,
) -> list[str]:
    normalized_segments = _normalize_segments(segments)
    if not normalized_segments:
        raise RuntimeError("render source video segments missing")

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for index, (start, end) in enumerate(normalized_segments):
        filter_parts.append(
            f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
        if include_audio:
            filter_parts.append(
                f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]"
            )
            concat_inputs.append(f"[a{index}]")

    if include_audio:
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={len(normalized_segments)}:v=1:a=1[outv][outa]"
        )
    else:
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={len(normalized_segments)}:v=1:a=0[outv]"
        )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[outv]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    if include_audio:
        command.extend(
            [
                "-map",
                "[outa]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    else:
        command.append("-an")
    command.append(str(output_path))
    return command


def generate_cut_source_video_to_browser_compatible_mp4(
    *,
    input_path: Path,
    output_path: Path,
    segments: Iterable[dict[str, object]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    include_audio = _probe_primary_audio_stream(input_path)
    command = build_cut_source_video_command(
        input_path=input_path,
        output_path=output_path,
        segments=segments,
        include_audio=include_audio,
    )
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output_path.exists():
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"ffmpeg exited with code {result.returncode}"
        raise RuntimeError(f"生成导出中间视频失败：{detail}")
