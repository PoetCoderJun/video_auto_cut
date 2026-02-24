from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..constants import ALLOWED_VIDEO_EXTENSIONS
from ..errors import unsupported_video_format


def validate_video_extension(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise unsupported_video_format(
            "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。"
        )


def ensure_ffprobe_available() -> str:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise RuntimeError("ffprobe not found in PATH")
    return ffprobe_bin


def _parse_rate(rate: object) -> float | None:
    if rate is None:
        return None
    raw = str(rate).strip()
    if not raw or raw == "0/0":
        return None
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            num_f = float(num)
            den_f = float(den)
        except ValueError:
            return None
        if den_f == 0:
            return None
        return num_f / den_f
    try:
        return float(raw)
    except ValueError:
        return None


def probe_video_stream(path: Path) -> dict[str, str | float | int | None]:
    ffprobe_bin = ensure_ffprobe_available()
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,r_frame_rate:format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise unsupported_video_format(
            "这个视频暂时无法处理。请重新导出为 MP4（推荐 H.264 编码）后再上传。"
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise unsupported_video_format(
            "这个视频暂时无法处理。请重新导出为 MP4（推荐 H.264 编码）后再上传。"
        ) from exc

    streams = payload.get("streams") or []
    if not streams:
        raise unsupported_video_format(
            "这个视频暂时无法处理。请重新导出为 MP4（推荐 H.264 编码）后再上传。"
        )

    codec_name = streams[0].get("codec_name")
    width = streams[0].get("width")
    height = streams[0].get("height")
    fps = _parse_rate(streams[0].get("avg_frame_rate")) or _parse_rate(streams[0].get("r_frame_rate"))
    duration = None
    try:
        duration_raw = (payload.get("format") or {}).get("duration")
        if duration_raw is not None:
            duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = None

    return {
        "video_codec": codec_name,
        "duration_sec": duration,
        "width": int(width) if isinstance(width, int) else None,
        "height": int(height) if isinstance(height, int) else None,
        "fps": float(fps) if fps is not None else None,
    }
