#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        raise exc

def extract_with_ffmpeg(input_path: Path, output_path: Path, sample_rate: int, mono: bool):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
    ]
    if mono:
        cmd += ["-ac", "1"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    cmd += [str(output_path)]
    run(cmd)

def extract_with_afconvert(input_path: Path, output_path: Path, sample_rate: int, mono: bool):
    # afconvert supports extracting audio tracks from .mov on macOS
    # -f WAVE: WAV container
    # -d LEI16: 16-bit little endian PCM
    cmd = ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16"]
    if sample_rate:
        cmd += ["-r", str(sample_rate)]
    if mono:
        cmd += ["-c", "1"]
    cmd += [str(input_path), str(output_path)]
    run(cmd)

def main():
    parser = argparse.ArgumentParser(description="Extract audio from a video file.")
    parser.add_argument("input", help="Path to input video file")
    parser.add_argument(
        "-o",
        "--output",
        help="Path to output audio file (default: same name .wav)",
    )
    parser.add_argument("--sample-rate", type=int, default=16000, help="Output sample rate")
    parser.add_argument("--mono", action="store_true", help="Downmix to mono")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output).expanduser().resolve() if args.output else input_path.with_suffix(".wav")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print("Using ffmpeg to extract audio...")
        extract_with_ffmpeg(input_path, output_path, args.sample_rate, args.mono)
    else:
        print("ffmpeg not found, using macOS afconvert...")
        extract_with_afconvert(input_path, output_path, args.sample_rate, args.mono)

    print(f"Wrote: {output_path}")

if __name__ == "__main__":
    main()
