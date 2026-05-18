from __future__ import annotations

import subprocess
from pathlib import Path


def transcode_source_video_to_browser_compatible_mp4(
    *,
    input_path: Path,
    output_path: Path,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]
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
        raise RuntimeError(f"服务端转码失败：{detail}")
