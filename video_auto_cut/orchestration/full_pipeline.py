#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

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


def _build_transcribe_args(args: argparse.Namespace, video_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(video_path)],
        force=bool(args.force),
        encoding=args.encoding,
        transcribe=True,
        qwen3_model=args.qwen3_model,
        qwen3_aligner=args.qwen3_aligner,
        qwen3_language=args.qwen3_language,
        qwen3_use_modelscope=bool(args.qwen3_use_modelscope),
        qwen3_offline=bool(args.qwen3_offline),
        qwen3_gap=float(args.qwen3_gap),
        qwen3_max_seg=float(args.qwen3_max_seg),
        qwen3_max_chars=int(args.qwen3_max_chars),
        qwen3_no_speech_gap=float(args.qwen3_no_speech_gap),
        qwen3_use_punct=bool(args.qwen3_use_punct),
        device=args.device,
        lang=args.lang,
        prompt=args.prompt,
    )


def _build_auto_edit_args(args: argparse.Namespace, srt_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(srt_path)],
        force=bool(args.force),
        encoding=args.encoding,
        auto_edit=True,
        auto_edit_llm=True,
        auto_edit_merge_gap=float(args.auto_edit_merge_gap),
        auto_edit_pad_head=float(args.auto_edit_pad_head),
        auto_edit_pad_tail=float(args.auto_edit_pad_tail),
        auto_edit_output=None,
        auto_edit_topics=False,
        llm_base_url=_resolve_llm_base_url(args),
        llm_model=_resolve_llm_model(args),
        llm_api_key=_resolve_llm_api_key(args),
        llm_timeout=int(args.llm_timeout),
        llm_temperature=float(args.llm_temperature),
        llm_max_tokens=int(args.llm_max_tokens),
        topic_output=None,
        topic_strict=bool(args.topic_strict),
        topic_max_topics=int(args.topic_max_topics),
        topic_summary_max_chars=int(args.topic_summary_max_chars),
    )


def _build_render_args(
    args: argparse.Namespace, video_path: Path, optimized_srt_path: Path
) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(video_path), str(optimized_srt_path)],
        encoding=args.encoding,
        bitrate=args.bitrate,
        cut_merge_gap=float(args.cut_merge_gap),
        render=True,
        render_output=args.render_output,
        render_cut_srt_output=args.render_cut_srt_output,
        render_topics=bool(args.render_topics),
        render_fps=args.render_fps,
        render_preview=bool(args.render_preview),
        render_codec=args.render_codec,
        render_crf=args.render_crf,
        topic_output=args.topic_output,
        topic_strict=bool(args.topic_strict),
        topic_max_topics=int(args.topic_max_topics),
        topic_summary_max_chars=int(args.topic_summary_max_chars),
        llm_base_url=_resolve_llm_base_url(args),
        llm_model=_resolve_llm_model(args),
        llm_api_key=_resolve_llm_api_key(args),
        llm_timeout=int(args.llm_timeout),
        llm_temperature=float(args.llm_temperature),
        llm_max_tokens=int(args.llm_max_tokens),
    )


def _require_llm(args: argparse.Namespace, stage_name: str) -> None:
    if not _resolve_llm_base_url(args) or not _resolve_llm_model(args):
        raise RuntimeError(
            f"{stage_name} requires LLM config: --llm-base-url and --llm-model, "
            "or set LLM_BASE_URL/LLM_MODEL in .env."
        )


def _resolve_llm_base_url(args: argparse.Namespace) -> Optional[str]:
    return (args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip() or None


def _resolve_llm_model(args: argparse.Namespace) -> Optional[str]:
    return (args.llm_model or os.environ.get("LLM_MODEL") or "").strip() or None


def _resolve_llm_api_key(args: argparse.Namespace) -> Optional[str]:
    return (
        args.llm_api_key
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or None
    )


def _run_transcribe(args: argparse.Namespace, video_path: Path) -> Path:
    from video_auto_cut.asr.transcribe import Transcribe

    logging.info("Step 1/3: transcribe -> SRT")
    transcribe_args = _build_transcribe_args(args, video_path)
    Transcribe(transcribe_args).run()
    srt_path = video_path.with_suffix(".srt")
    if not srt_path.exists():
        raise RuntimeError(f"Transcribe step did not produce SRT: {srt_path}")
    return srt_path


def _run_auto_edit(args: argparse.Namespace, srt_path: Path) -> Path:
    from video_auto_cut.editing.auto_edit import AutoEdit

    _require_llm(args, "Auto-edit")
    logging.info("Step 2/3: auto edit -> optimized SRT")
    auto_edit_args = _build_auto_edit_args(args, srt_path)
    AutoEdit(auto_edit_args).run()
    optimized = srt_path.with_name(f"{srt_path.stem}.optimized.srt")
    if not optimized.exists():
        raise RuntimeError(f"Auto-edit step did not produce optimized SRT: {optimized}")
    return optimized


def _run_render(
    args: argparse.Namespace, video_path: Path, optimized_srt_path: Path
) -> None:
    from video_auto_cut.rendering.remotion_renderer import RemotionRenderer

    if args.render_topics:
        _require_llm(args, "Render topic segmentation")
    logging.info("Step 3/3: remotion render")
    render_args = _build_render_args(args, video_path, optimized_srt_path)
    RemotionRenderer(render_args).run()


def _resolve_render_output_path(args: argparse.Namespace, video_path: Path) -> Path:
    if args.render_output:
        return Path(args.render_output).expanduser().resolve()
    return video_path.with_name(f"{video_path.stem}_remotion.mp4")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full pipeline: transcribe -> auto-edit -> remotion render."
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
    parser.add_argument(
        "--skip-render",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Skip render step",
    )

    parser.add_argument("--encoding", type=str, default="utf-8")
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force rerun even if intermediate/final outputs already exist",
    )
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument(
        "--lang",
        type=str,
        default="Chinese",
        help="ASR language, e.g. Chinese/English or zh/en alias (default: Chinese)",
    )
    parser.add_argument("--prompt", type=str, default="")

    parser.add_argument("--qwen3-model", type=str, default="./model/Qwen3-ASR-0.6B")
    parser.add_argument(
        "--qwen3-aligner",
        type=str,
        default="./model/Qwen3-ForcedAligner-0.6B",
    )
    parser.add_argument(
        "--qwen3-language",
        type=str,
        default=None,
        help="Override ASR language; supports canonical names and zh/en aliases",
    )
    parser.add_argument(
        "--qwen3-use-modelscope",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--qwen3-offline",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--qwen3-gap", type=float, default=0.6)
    parser.add_argument("--qwen3-max-seg", type=float, default=20.0)
    parser.add_argument("--qwen3-max-chars", type=int, default=0)
    parser.add_argument("--qwen3-no-speech-gap", type=float, default=1.0)
    parser.add_argument(
        "--qwen3-use-punct",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    parser.add_argument("--llm-base-url", type=str, default=None)
    parser.add_argument("--llm-model", type=str, default=None)
    parser.add_argument("--llm-api-key", type=str, default=None)
    parser.add_argument("--llm-timeout", type=int, default=60)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    parser.add_argument("--llm-max-tokens", type=int, default=4096)

    parser.add_argument("--auto-edit-merge-gap", type=float, default=0.5)
    parser.add_argument("--auto-edit-pad-head", type=float, default=0.0)
    parser.add_argument("--auto-edit-pad-tail", type=float, default=0.0)

    parser.add_argument("--bitrate", type=str, default="10m")
    parser.add_argument("--cut-merge-gap", type=float, default=0.0)
    parser.add_argument("--render-output", type=str, default=None)
    parser.add_argument("--render-cut-srt-output", type=str, default=None)
    parser.add_argument("--render-fps", type=float, default=None)
    parser.add_argument(
        "--render-preview",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--render-codec", type=str, default=None)
    parser.add_argument("--render-crf", type=int, default=None)
    parser.add_argument(
        "--render-topics",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--topic-output", type=str, default=None)
    parser.add_argument("--topic-max-topics", type=int, default=8)
    parser.add_argument("--topic-summary-max-chars", type=int, default=6)
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
    render_output_path = _resolve_render_output_path(args, video_path)

    if not args.skip_transcribe:
        if srt_path.exists() and not args.force:
            logging.info("Step 1/3: skip transcribe (exists): %s", srt_path)
        else:
            srt_path = _run_transcribe(args, video_path)
    elif not srt_path.exists():
        raise FileNotFoundError(
            f"Missing SRT while --skip-transcribe is set: {srt_path}"
        )

    if not args.skip_auto_edit:
        if optimized_path.exists() and not args.force:
            logging.info("Step 2/3: skip auto edit (exists): %s", optimized_path)
        else:
            optimized_path = _run_auto_edit(args, srt_path)
    elif not optimized_path.exists():
        raise FileNotFoundError(
            f"Missing optimized SRT while --skip-auto-edit is set: {optimized_path}"
        )

    if not args.skip_render:
        if render_output_path.exists() and not args.force:
            logging.info("Step 3/3: skip remotion render (exists): %s", render_output_path)
        else:
            _run_render(args, video_path, optimized_path)

    logging.info("Done")
    logging.info("SRT: %s", srt_path)
    logging.info("Optimized SRT: %s", optimized_path)


if __name__ == "__main__":
    main()
