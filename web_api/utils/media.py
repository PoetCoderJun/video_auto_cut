from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..constants import ALLOWED_VIDEO_EXTENSIONS
from ..errors import unsupported_video_format


def validate_video_extension(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise unsupported_video_format("仅支持 mp4/mov/mkv/avi/webm/flv/f4v")


def ensure_ffprobe_available() -> str:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise RuntimeError("ffprobe not found in PATH")
    return ffprobe_bin


def probe_video_stream(path: Path) -> dict[str, str | float | None]:
    ffprobe_bin = ensure_ffprobe_available()
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name:format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise unsupported_video_format("视频文件无法读取，请重新导出后上传")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise unsupported_video_format("视频文件无法读取，请重新导出后上传") from exc

    streams = payload.get("streams") or []
    if not streams:
        raise unsupported_video_format("视频文件无法读取，请重新导出后上传")

    codec_name = streams[0].get("codec_name")
    duration = None
    try:
        duration_raw = (payload.get("format") or {}).get("duration")
        if duration_raw is not None:
            duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = None

    return {"video_codec": codec_name, "duration_sec": duration}
