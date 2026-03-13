#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_STR = str(REPO_ROOT)
if REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, REPO_ROOT_STR)

from video_auto_cut.human_loop import (
    approve_step1,
    approve_step2,
    derive_artifact_root,
    ensure_paths,
    load_state,
    render_output,
    run_until_human_gate,
)
from video_auto_cut.orchestration.pipeline_service import PipelineOptions

_ENV_LOADED = False


def _ensure_local_package_import() -> None:
    if REPO_ROOT_STR not in sys.path:
        sys.path.insert(0, REPO_ROOT_STR)


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
        if key and key not in os.environ:
            os.environ[key] = value


def _auto_load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if candidate.exists():
            _load_env_file(candidate)
            break
    _ENV_LOADED = True


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[human-loop] %(levelname)s %(message)s")


def _env(value: str, default: str = "") -> str:
    return (os.getenv(value) or default).strip()


def _env_bool(value: str, default: bool = False) -> bool:
    raw = _env(value, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _env_float(value: str, default: float) -> float:
    raw = _env(value)
    return float(raw) if raw else float(default)


def _env_int(value: str, default: int) -> int:
    raw = _env(value)
    return int(raw) if raw else int(default)


def _build_options(args: argparse.Namespace) -> PipelineOptions:
    return PipelineOptions(
        encoding=args.encoding,
        force=bool(args.force),
        lang=args.lang,
        prompt=args.prompt,
        asr_backend="dashscope_filetrans",
        asr_dashscope_base_url=args.asr_dashscope_base_url or _env("ASR_DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com"),
        asr_dashscope_model=args.asr_dashscope_model or _env("ASR_DASHSCOPE_MODEL", "qwen3-asr-flash-filetrans"),
        asr_dashscope_task=args.asr_dashscope_task or _env("ASR_DASHSCOPE_TASK"),
        asr_dashscope_api_key=args.asr_dashscope_api_key or _env("ASR_DASHSCOPE_API_KEY") or _env("DASHSCOPE_API_KEY") or None,
        asr_dashscope_poll_seconds=_env_float("ASR_DASHSCOPE_POLL_SECONDS", 2.0),
        asr_dashscope_timeout_seconds=_env_float("ASR_DASHSCOPE_TIMEOUT_SECONDS", 3600.0),
        asr_dashscope_language_hints=tuple(item.strip() for item in _env("ASR_DASHSCOPE_LANGUAGE_HINTS").split(",") if item.strip()),
        asr_dashscope_context=_env("ASR_DASHSCOPE_CONTEXT"),
        asr_dashscope_enable_words=_env_bool("ASR_DASHSCOPE_ENABLE_WORDS", True),
        asr_dashscope_sentence_rule_with_punc=_env_bool("ASR_DASHSCOPE_SENTENCE_RULE_WITH_PUNC", True),
        asr_dashscope_word_split_enabled=_env_bool("ASR_DASHSCOPE_WORD_SPLIT_ENABLED", True),
        asr_dashscope_word_split_on_comma=_env_bool("ASR_DASHSCOPE_WORD_SPLIT_ON_COMMA", True),
        asr_dashscope_word_split_comma_pause_s=_env_float("ASR_DASHSCOPE_WORD_SPLIT_COMMA_PAUSE_S", 0.4),
        asr_dashscope_word_split_min_chars=_env_int("ASR_DASHSCOPE_WORD_SPLIT_MIN_CHARS", 12),
        asr_dashscope_word_vad_gap_s=_env_float("ASR_DASHSCOPE_WORD_VAD_GAP_S", 1.0),
        asr_dashscope_word_max_segment_s=_env_float("ASR_DASHSCOPE_WORD_MAX_SEGMENT_S", 8.0),
        asr_dashscope_no_speech_gap_s=_env_float("ASR_DASHSCOPE_NO_SPEECH_GAP_S", 1.0),
        asr_dashscope_insert_no_speech=_env_bool("ASR_DASHSCOPE_INSERT_NO_SPEECH", True),
        asr_dashscope_insert_head_no_speech=_env_bool("ASR_DASHSCOPE_INSERT_HEAD_NO_SPEECH", True),
        asr_oss_endpoint=_env("OSS_ENDPOINT") or None,
        asr_oss_bucket=_env("OSS_BUCKET") or None,
        asr_oss_access_key_id=_env("OSS_ACCESS_KEY_ID") or None,
        asr_oss_access_key_secret=_env("OSS_ACCESS_KEY_SECRET") or None,
        asr_oss_prefix=_env("OSS_AUDIO_PREFIX", "video-auto-cut/asr"),
        asr_oss_signed_url_ttl_seconds=_env_int("OSS_SIGNED_URL_TTL_SECONDS", 86400),
        use_dashscope_temp_oss=_env_bool("USE_DASHSCOPE_TEMP_OSS", False),
        llm_base_url=args.llm_base_url or _env("LLM_BASE_URL") or None,
        llm_model=args.llm_model or _env("LLM_MODEL") or None,
        topic_llm_model=args.topic_llm_model or _env("TOPIC_LLM_MODEL") or None,
        llm_api_key=args.llm_api_key or _env("LLM_API_KEY") or _env("DASHSCOPE_API_KEY") or None,
        llm_timeout=int(args.llm_timeout),
        llm_temperature=float(args.llm_temperature),
        llm_max_tokens=int(args.llm_max_tokens) if args.llm_max_tokens is not None else None,
        auto_edit_merge_gap=float(args.auto_edit_merge_gap),
        auto_edit_pad_head=float(args.auto_edit_pad_head),
        auto_edit_pad_tail=float(args.auto_edit_pad_tail),
        bitrate=args.bitrate,
        cut_merge_gap=float(args.cut_merge_gap),
        topic_output=None,
        topic_strict=bool(args.topic_strict),
        topic_max_topics=int(args.topic_max_topics),
        topic_title_max_chars=int(args.topic_title_max_chars),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Human-in-the-loop wrapper for the video auto cut pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--input-video", type=str, default=None)
        subparser.add_argument("--artifact-root", type=str, default=None)

    run_parser = subparsers.add_parser("run", help="Run until the next human review gate.")
    add_common(run_parser)
    run_parser.add_argument("--output-video", type=str, required=True)

    approve_step1_parser = subparsers.add_parser("approve-step1", help="Approve or apply edited step1 lines.")
    add_common(approve_step1_parser)
    approve_step1_parser.add_argument("--review-json", type=str, default=None)

    approve_step2_parser = subparsers.add_parser("approve-step2", help="Approve or apply edited step2 chapters.")
    add_common(approve_step2_parser)
    approve_step2_parser.add_argument("--review-json", type=str, default=None)

    render_parser = subparsers.add_parser("render", help="Render the final cut after both human gates.")
    add_common(render_parser)

    status_parser = subparsers.add_parser("status", help="Show current human-loop status.")
    add_common(status_parser)

    parser.add_argument("--encoding", type=str, default="utf-8")
    parser.add_argument("--force", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--lang", type=str, default="Chinese")
    parser.add_argument("--prompt", type=str, default="")
    parser.add_argument("--asr-dashscope-base-url", type=str, default=None)
    parser.add_argument("--asr-dashscope-model", type=str, default=None)
    parser.add_argument("--asr-dashscope-task", type=str, default=None)
    parser.add_argument("--asr-dashscope-api-key", type=str, default=None)
    parser.add_argument("--llm-base-url", type=str, default=None)
    parser.add_argument("--llm-model", type=str, default=None)
    parser.add_argument("--topic-llm-model", type=str, default=None)
    parser.add_argument("--llm-api-key", type=str, default=None)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    parser.add_argument("--llm-max-tokens", type=int, default=None)
    parser.add_argument("--auto-edit-merge-gap", type=float, default=0.5)
    parser.add_argument("--auto-edit-pad-head", type=float, default=0.0)
    parser.add_argument("--auto-edit-pad-tail", type=float, default=0.0)
    parser.add_argument("--bitrate", type=str, default="10m")
    parser.add_argument("--cut-merge-gap", type=float, default=0.0)
    parser.add_argument("--topic-strict", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--topic-max-topics", type=int, default=5)
    parser.add_argument("--topic-title-max-chars", type=int, default=6)
    return parser.parse_args()


def _resolve_input_video(args: argparse.Namespace) -> Path:
    if args.input_video:
        path = Path(args.input_video).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"input video not found: {path}")
        return path
    if args.artifact_root:
        state_path = Path(args.artifact_root).expanduser().resolve() / "state.json"
        if not state_path.exists():
            raise RuntimeError(f"state file not found: {state_path}")
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        state = payload if isinstance(payload, dict) else {}
        raw_path = str(state.get("input_video_path") or "").strip()
        if raw_path:
            path = Path(raw_path).expanduser().resolve()
            if path.exists():
                return path
    raise RuntimeError("provide --input-video or an --artifact-root with an existing state.json")


def main() -> None:
    _ensure_local_package_import()
    _auto_load_dotenv()
    _setup_logging()
    args = _parse_args()

    input_video_path = _resolve_input_video(args)
    artifact_root = args.artifact_root or str(derive_artifact_root(input_video_path))

    if args.command == "status":
        state = load_state(ensure_paths(input_video_path, artifact_root))
        logging.info("artifact_root=%s", artifact_root)
        logging.info("state=%s", state or {"status": "NOT_INITIALIZED"})
        return

    options = _build_options(args)
    if args.command == "run":
        state = run_until_human_gate(
            input_video_path=input_video_path,
            output_video_path=Path(args.output_video).expanduser().resolve(),
            artifact_root=artifact_root,
            options=options,
        )
    elif args.command == "approve-step1":
        state = approve_step1(
            input_video_path=input_video_path,
            artifact_root=artifact_root,
            review_json_path=Path(args.review_json).expanduser().resolve() if args.review_json else None,
            encoding=args.encoding,
        )
    elif args.command == "approve-step2":
        state = approve_step2(
            input_video_path=input_video_path,
            artifact_root=artifact_root,
            review_json_path=Path(args.review_json).expanduser().resolve() if args.review_json else None,
        )
    else:
        state = render_output(
            input_video_path=input_video_path,
            artifact_root=artifact_root,
            options=options,
        )
    logging.info("status=%s artifact_root=%s", state.get("status"), artifact_root)


if __name__ == "__main__":
    main()
