#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .pipeline_options_builder import build_pipeline_options_from_env
from .pipeline_service import (
    PipelineOptions,
    run_auto_edit,
    run_transcribe,
)

_ENV_LOADED = False


def _ensure_local_package_import() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_env_file(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not key or key in os.environ:
            continue
        os.environ[key] = value


def _auto_load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for candidate in candidates:
        if candidate.exists():
            _load_env_file(candidate)
            break
    _ENV_LOADED = True


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[pipeline] %(levelname)s %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full pipeline: transcribe -> auto-edit."
    )
    parser.add_argument("video", type=str, help="Input video path")

    parser.add_argument(
        "--skip-transcribe",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Skip transcribe step (expects existing .srt)",
    )
    parser.add_argument(
        "--skip-auto-edit",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Skip auto-edit step (expects existing .optimized.srt)",
    )
    parser.add_argument("--encoding", type=str, default="utf-8")
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force rerun even if intermediate/final outputs already exist",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="Chinese",
        help="ASR language, e.g. Chinese/English or zh/en alias (default: Chinese)",
    )
    parser.add_argument("--prompt", type=str, default="")

    parser.add_argument("--llm-base-url", type=str, default=None)
    parser.add_argument("--llm-model", type=str, default=None)
    parser.add_argument("--llm-api-key", type=str, default=None)
    parser.add_argument("--asr-backend", type=str, default=None)
    parser.add_argument("--asr-dashscope-base-url", type=str, default=None)
    parser.add_argument("--asr-dashscope-model", type=str, default=None)
    parser.add_argument("--asr-dashscope-api-key", type=str, default=None)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=None,
        help="Optional LLM max tokens for responses (omit to use model default)",
    )

    parser.add_argument("--auto-edit-merge-gap", type=float, default=0.5)
    parser.add_argument("--auto-edit-pad-head", type=float, default=0.0)
    parser.add_argument("--auto-edit-pad-tail", type=float, default=0.0)

    parser.add_argument("--bitrate", type=str, default="10m")
    parser.add_argument("--cut-merge-gap", type=float, default=0.0)
    parser.add_argument("--topic-output", type=str, default=None)
    parser.add_argument("--topic-max-topics", type=int, default=5)
    parser.add_argument("--topic-title-max-chars", type=int, default=6)
    parser.add_argument(
        "--topic-strict",
        action=argparse.BooleanOptionalAction,
        default=False,
    )

    return parser.parse_args()


def main() -> None:
    _ensure_local_package_import()
    _auto_load_dotenv()
    _setup_logging()
    args = _parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Input video not found: {video_path}")

    srt_path = video_path.with_suffix(".srt")
    optimized_path = srt_path.with_name(f"{srt_path.stem}.optimized.srt")

    if not args.skip_transcribe:
        if srt_path.exists() and not args.force:
            logging.info("Step 1/2: skip transcribe (exists): %s", srt_path)
        else:
            options = build_pipeline_options_from_env(
                encoding=args.encoding,
                force=bool(args.force),
                lang=args.lang,
                prompt=args.prompt,
                asr_backend=(args.asr_backend or os.environ.get("ASR_BACKEND") or "dashscope_filetrans").strip() or "dashscope_filetrans",
                asr_dashscope_base_url=(args.asr_dashscope_base_url or "").strip() or None,
                asr_dashscope_model=(args.asr_dashscope_model or "").strip() or None,
                asr_dashscope_api_key=(args.asr_dashscope_api_key or os.environ.get("DASHSCOPE_ASR_API_KEY") or os.environ.get("ASR_DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or None),
                llm_base_url=(args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip() or None,
                llm_model=(args.llm_model or os.environ.get("LLM_MODEL") or "").strip() or None,
                llm_api_key=(args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or None),
                llm_timeout=int(args.llm_timeout),
                llm_temperature=float(args.llm_temperature),
                llm_max_tokens=int(args.llm_max_tokens) if args.llm_max_tokens is not None else None,
                auto_edit_merge_gap=float(args.auto_edit_merge_gap),
                auto_edit_pad_head=float(args.auto_edit_pad_head),
                auto_edit_pad_tail=float(args.auto_edit_pad_tail),
                bitrate=args.bitrate,
                cut_merge_gap=float(args.cut_merge_gap),
                topic_output=args.topic_output,
                topic_strict=bool(args.topic_strict),
                topic_max_topics=int(args.topic_max_topics),
                topic_title_max_chars=int(args.topic_title_max_chars),
            )
            srt_path = run_transcribe(video_path, options)
    elif not srt_path.exists():
        raise FileNotFoundError(
            f"Missing SRT while --skip-transcribe is set: {srt_path}"
        )

    if not args.skip_auto_edit:
        if optimized_path.exists() and not args.force:
            logging.info("Step 2/2: skip auto edit (exists): %s", optimized_path)
        else:
            options = build_pipeline_options_from_env(
                encoding=args.encoding,
                force=bool(args.force),
                lang=args.lang,
                prompt=args.prompt,
                asr_backend=(args.asr_backend or os.environ.get("ASR_BACKEND") or "dashscope_filetrans").strip() or "dashscope_filetrans",
                asr_dashscope_base_url=(args.asr_dashscope_base_url or "").strip() or None,
                asr_dashscope_model=(args.asr_dashscope_model or "").strip() or None,
                asr_dashscope_api_key=(args.asr_dashscope_api_key or os.environ.get("DASHSCOPE_ASR_API_KEY") or os.environ.get("ASR_DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or None),
                llm_base_url=(args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip() or None,
                llm_model=(args.llm_model or os.environ.get("LLM_MODEL") or "").strip() or None,
                llm_api_key=(args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or None),
                llm_timeout=int(args.llm_timeout),
                llm_temperature=float(args.llm_temperature),
                llm_max_tokens=int(args.llm_max_tokens) if args.llm_max_tokens is not None else None,
                auto_edit_merge_gap=float(args.auto_edit_merge_gap),
                auto_edit_pad_head=float(args.auto_edit_pad_head),
                auto_edit_pad_tail=float(args.auto_edit_pad_tail),
                bitrate=args.bitrate,
                cut_merge_gap=float(args.cut_merge_gap),
                topic_output=args.topic_output,
                topic_strict=bool(args.topic_strict),
                topic_max_topics=int(args.topic_max_topics),
                topic_title_max_chars=int(args.topic_title_max_chars),
            )
            optimized_path = run_auto_edit(srt_path, options).optimized_srt_path
    elif not optimized_path.exists():
        raise FileNotFoundError(
            f"Missing optimized SRT while --skip-auto-edit is set: {optimized_path}"
        )

    logging.info("Done")
    logging.info("SRT: %s", srt_path)
    logging.info("Optimized SRT: %s", optimized_path)


if __name__ == "__main__":
    main()
