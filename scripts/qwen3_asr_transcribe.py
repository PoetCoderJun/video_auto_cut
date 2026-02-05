#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Avoid numba issues from librosa on some macOS setups.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.abspath(".cache/numba"))

import numpy as np
import torch
from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner


def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        raise exc


def ensure_audio(input_path: Path, work_dir: Path, sample_rate: int, mono: bool) -> Path:
    ext = input_path.suffix.lower()
    is_audio = ext in {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg"}
    if is_audio and not mono and not sample_rate:
        return input_path

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found; please install it or extract audio first.")

    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / (input_path.stem + ".wav")

    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    if mono:
        cmd += ["-ac", "1"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    cmd += [str(out_path)]
    run(cmd)
    return out_path


def load_audio_tuple(audio_path: Path, sample_rate: int) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("soundfile is required to load audio without librosa.") from exc

    audio, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    sr = int(sr)
    if sample_rate and sr != sample_rate:
        raise RuntimeError(
            f"Audio sample rate is {sr}, expected {sample_rate}. "
            "Re-run extraction with --sample-rate or use ffmpeg to resample."
        )
    return audio, sr


def load_asr_model(model_id: str, device: str, dtype, offline: bool):
    return Qwen3ASRModel.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        max_inference_batch_size=1,
        max_new_tokens=512,
        local_files_only=offline,
    )


def load_aligner(model_id: str, device: str, dtype, offline: bool):
    return Qwen3ForcedAligner.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        local_files_only=offline,
    )


def try_load_with_fallback(load_fn, model_id: str, offline: bool, label: str):
    model = None
    try:
        if torch.backends.mps.is_available():
            print(f"Trying MPS for {label}...")
            model = load_fn(model_id, "mps", torch.float16, offline)
        else:
            print("MPS not available, will use CPU.")
    except Exception as exc:
        print(f"MPS failed for {label}: {exc}")
        model = None

    if model is None:
        print(f"Using CPU for {label}...")
        model = load_fn(model_id, "cpu", torch.float32, offline)
    return model


def segment_to_dict(seg):
    if isinstance(seg, dict):
        text = seg.get("text") or seg.get("token")
        start = seg.get("start_time") or seg.get("start")
        end = seg.get("end_time") or seg.get("end")
        out = {"text": text, "start": start, "end": end}
        if "score" in seg:
            out["score"] = seg.get("score")
        if "confidence" in seg:
            out["confidence"] = seg.get("confidence")
        return out

    text = getattr(seg, "text", None)
    start = getattr(seg, "start_time", None)
    end = getattr(seg, "end_time", None)
    if start is None:
        start = getattr(seg, "start", None)
    if end is None:
        end = getattr(seg, "end", None)

    if text is None and isinstance(seg, (list, tuple)) and len(seg) >= 3:
        text, start, end = seg[0], seg[1], seg[2]

    out = {"text": text, "start": start, "end": end}
    score = getattr(seg, "score", None)
    confidence = getattr(seg, "confidence", None)
    if score is not None:
        out["score"] = score
    if confidence is not None:
        out["confidence"] = confidence
    return out


def flatten_alignment(alignment):
    if not alignment:
        return []
    if isinstance(alignment, list) and alignment:
        first = alignment[0]
        if hasattr(first, "items"):
            return [segment_to_dict(seg) for seg in first.items]
        if isinstance(first, list):
            return [segment_to_dict(seg) for seg in first]
        return [segment_to_dict(seg) for seg in alignment]
    if hasattr(alignment, "items"):
        return [segment_to_dict(seg) for seg in alignment.items]
    return [segment_to_dict(seg) for seg in alignment]


def resolve_model_path(model_id_or_path: str, use_modelscope: bool) -> str:
    candidate = Path(model_id_or_path).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    if not use_modelscope:
        return model_id_or_path
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "modelscope is not installed. Run: pip install -U modelscope"
        ) from exc
    return snapshot_download(model_id_or_path)


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio or video with Qwen3-ASR.")
    parser.add_argument("input", help="Path to audio/video file")
    parser.add_argument("--model", default="Qwen/Qwen3-ASR-0.6B", help="ASR model id or local path")
    parser.add_argument(
        "--aligner",
        default=None,
        help="Forced aligner model id or local path (enable timestamps)",
    )
    parser.add_argument(
        "--use-modelscope",
        action="store_true",
        help="Resolve model ids via ModelScope snapshot_download",
    )
    parser.add_argument("--language", default=None, help="Force language or leave empty for auto")
    parser.add_argument("--work-dir", default=".cache/qwen3_asr", help="Where to put extracted audio")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for extraction")
    parser.add_argument("--mono", action="store_true", help="Downmix to mono for extraction")
    parser.add_argument("--offline", action="store_true", help="Do not access network; use local files only")
    parser.add_argument("--output", default=None, help="Write JSON result to this file")
    args = parser.parse_args()

    if args.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    work_dir = Path(args.work_dir).expanduser().resolve()

    audio_path = ensure_audio(input_path, work_dir, args.sample_rate, args.mono)
    audio_tuple = load_audio_tuple(audio_path, args.sample_rate)

    resolved_model = resolve_model_path(args.model, args.use_modelscope)
    resolved_aligner = resolve_model_path(args.aligner, args.use_modelscope) if args.aligner else None

    asr_model = try_load_with_fallback(load_asr_model, resolved_model, args.offline, "ASR")
    results = asr_model.transcribe(audio=audio_tuple, language=args.language)
    asr = results[0]

    output = {
        "audio": str(audio_path),
        "language": asr.language,
        "text": asr.text,
        "asr_model": resolved_model,
    }

    if resolved_aligner:
        aligner = try_load_with_fallback(load_aligner, resolved_aligner, args.offline, "Aligner")
        align_kwargs = {"audio": audio_tuple, "text": asr.text}
        align_language = args.language or asr.language
        if align_language:
            align_kwargs["language"] = align_language
        alignment = aligner.align(**align_kwargs)
        output["timestamps"] = flatten_alignment(alignment)
        output["aligner_model"] = resolved_aligner

    output_json = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"Wrote: {output_path}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
