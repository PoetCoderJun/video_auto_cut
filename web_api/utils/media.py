from __future__ import annotations

from pathlib import Path

from ..constants import ALLOWED_AUDIO_EXTENSIONS
from ..errors import unsupported_audio_format


def validate_audio_extension(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise unsupported_audio_format(
            "这个音频格式暂不支持。请上传 M4A、MP3、WAV、AAC、FLAC、OGG/OPUS 或 MP4 音频。"
        )
