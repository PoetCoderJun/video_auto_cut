import logging
import os

import ffmpeg
import numpy as np


def load_audio(file: str, sr: int = 16000) -> np.ndarray:
    try:
        out, _ = (
            ffmpeg.input(file, threads=0)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=sr)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Failed to load audio: {exc.stderr.decode()}") from exc

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0


def is_video(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in [".mp4", ".mov", ".mkv", ".avi", ".flv", ".f4v", ".webm"]


def is_audio(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in [".ogg", ".wav", ".mp3", ".flac", ".m4a"]


def change_ext(filename: str, new_ext: str) -> str:
    base, _ = os.path.splitext(filename)
    if not new_ext.startswith("."):
        new_ext = "." + new_ext
    return base + new_ext


def add_cut(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    if base.endswith("_cut"):
        base = base[:-4] + "_" + base[-4:]
    else:
        base += "_cut"
    return base + ext


def check_exists(output: str, force: bool) -> bool:
    if os.path.exists(output):
        if force:
            logging.info("%s exists. Will overwrite it", output)
        else:
            logging.info("%s exists, skipping... Use --force to overwrite", output)
            return True
    return False
