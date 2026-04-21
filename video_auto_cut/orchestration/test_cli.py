from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import srt

from video_auto_cut.asr.transcribe_stage import run_asr_transcription_stage
from video_auto_cut.editing import llm_client as llm_utils
from video_auto_cut.editing.direct_prompts import build_review_messages
from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_env
from video_auto_cut.pi_agent_runner import (
    DEFAULT_MAX_LINES,
    PROJECT_ROOT,
    TestPiRequest,
    _render_chapters_text,
    _render_test_text_from_lines,
    _sort_runtime_lines,
    _write_json,
    build_pi_command,
    build_subtitles_from_lines,
    run_test_pi,
)
from video_auto_cut.rendering.subtitle_render_contract import (
    build_subtitle_style_llm_config,
    request_subtitle_style_contract,
)
from video_auto_cut.shared.test_text_io import build_test_lines_from_text


def _load_segments_from_path(input_path: Path, encoding: str) -> list[dict[str, Any]]:
    if input_path.suffix.lower() == ".srt":
        segments: list[dict[str, Any]] = []
        for sub in srt.parse(input_path.read_text(encoding=encoding)):
            segments.append(
                {
                    "id": int(sub.index),
                    "start": float(sub.start.total_seconds()),
                    "end": float(sub.end.total_seconds()),
                    "duration": max(0.0, float(sub.end.total_seconds() - sub.start.total_seconds())),
                    "text": str(sub.content or "").strip(),
                }
            )
        return segments
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        payload = payload["segments"]
    if not isinstance(payload, list):
        raise RuntimeError(f"Unsupported input payload for {input_path}")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": int(item.get("id") or item.get("line_id") or index),
                "start": float(item.get("start") or 0.0),
                "end": float(item.get("end") or 0.0),
                "duration": max(0.0, float(item.get("end") or 0.0) - float(item.get("start") or 0.0)),
                "text": str(item.get("text") or item.get("original_text") or "").strip(),
            }
        )
    return result


def _load_lines_from_test_text(input_path: Path) -> list[dict[str, Any]]:
    return _sort_runtime_lines(build_test_lines_from_text(input_path))


def _build_cli_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = {
        "base_url": (args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip(),
        "model": (args.llm_model or os.environ.get("LLM_MODEL") or "").strip(),
        "api_key": (args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip(),
        "timeout": int(args.llm_timeout),
        "max_tokens": args.llm_max_tokens,
    }
    if not cfg.get("base_url") or not cfg.get("model"):
        raise RuntimeError("LLM config missing. Set --llm-base-url and --llm-model.")
    return cfg




def _build_kept_captions_from_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for line in lines:
        if bool(line.get("user_final_remove", False)):
            continue
        text = str(line.get("optimized_text") or line.get("original_text") or "").strip()
        if not text:
            continue
        captions.append(
            {
                "index": len(captions) + 1,
                "start": float(line.get("start") or 0.0),
                "end": float(line.get("end") or 0.0),
                "text": text,
            }
        )
    return captions


def _build_cli_highlight_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    return build_subtitle_style_llm_config(
        base_url=(args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip() or None,
        model=(args.llm_model or os.environ.get("LLM_MODEL") or "").strip() or None,
        api_key=(args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip() or None,
        timeout=int(args.llm_timeout),
        max_tokens=args.llm_max_tokens,
    )


def _write_highlight_contract(path: Path, *, captions: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    payload = request_subtitle_style_contract(
        captions=captions,
        llm_config=_build_cli_highlight_llm_config(args),
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


REVIEW_MODEL = "qwen3.6-max-preview"


def _build_review_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    return llm_utils.build_llm_config(
        base_url=(args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip() or None,
        model=REVIEW_MODEL,
        api_key=(args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip() or None,
        timeout=int(args.llm_timeout),
        temperature=0.0,
        max_tokens=args.llm_max_tokens,
        enable_thinking=False,
    )


def _build_review_input(
    *,
    raw_lines: list[dict[str, Any]],
    final_lines: list[dict[str, Any]],
) -> str:
    raw_text = _render_test_text_from_lines(raw_lines)
    final_text = _render_test_text_from_lines(final_lines)
    return (
        "[原始转写]\n" + raw_text.strip() + "\n\n"
        "[delete+polish 最终稿]\n" + final_text.strip()
    )


def _write_review_report(
    path: Path,
    *,
    raw_lines: list[dict[str, Any]],
    final_lines: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    review_input = _build_review_input(
        raw_lines=raw_lines,
        final_lines=final_lines,
    )
    cfg = _build_review_llm_config(args)
    started = time.perf_counter()
    review_text = llm_utils.chat_completion(cfg, build_review_messages(review_input))
    elapsed = time.perf_counter() - started
    path.write_text(str(review_text or "").strip() + "\n", encoding="utf-8")
    return {
        "model": REVIEW_MODEL,
        "elapsed_seconds": round(elapsed, 3),
        "path": str(path),
    }

def _build_cli_pipeline_options(args: argparse.Namespace):
    return build_pipeline_options_from_env(
        force=True,
        lang=(args.lang or None),
        prompt=str(args.prompt or ""),
    )


def _write_srt(path: Path, subtitles: list[srt.Subtitle], encoding: str) -> None:
    path.write_text(srt.compose(subtitles, reindex=False), encoding=encoding)


def _run_cli_test(args: argparse.Namespace) -> int:
    llm_config = _build_cli_llm_config(args)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".json":
        raise RuntimeError("`--task test` currently expects media or .srt input, not .json")

    raw_srt_path: Path
    raw_lines: list[dict[str, Any]]
    if input_path.suffix.lower() == ".srt":
        raw_srt_path = input_path
        segments = _load_segments_from_path(input_path, args.encoding)
        raw_lines = [
            {
                "line_id": int(segment["id"]),
                "start": float(segment.get("start") or 0.0),
                "end": float(segment.get("end") or 0.0),
                "original_text": str(segment.get("text") or "").strip(),
                "optimized_text": str(segment.get("text") or "").strip(),
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
            for segment in segments
        ]
    else:
        asr_artifacts = run_asr_transcription_stage(
            input_path,
            _build_cli_pipeline_options(args),
        )
        raw_srt_path = asr_artifacts.srt_path
        raw_lines = asr_artifacts.test_lines
        segments = [
            {
                "id": int(line["line_id"]),
                "start": float(line["start"]),
                "end": float(line["end"]),
                "duration": max(0.0, float(line["end"]) - float(line["start"])),
                "text": str(line["original_text"]),
            }
            for line in raw_lines
        ]

    delete_artifacts = run_test_pi(
        TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)
    )
    polish_artifacts = run_test_pi(
        TestPiRequest(task="polish", llm_config=llm_config, lines=delete_artifacts.lines, max_lines=args.max_lines)
    )
    review_report_path = output_path.with_suffix(".review.txt")

    review_meta = _write_review_report(
        review_report_path,
        raw_lines=raw_lines,
        final_lines=polish_artifacts.lines,
        args=args,
    )

    chapter_artifacts = run_test_pi(
        TestPiRequest(
            task="chapter",
            llm_config=llm_config,
            lines=polish_artifacts.lines,
            title_max_chars=args.title_max_chars,
            max_lines=args.max_lines,
        )
    )

    raw_test_text_path = output_path.with_suffix(".raw.test.txt")
    final_test_text_path = output_path.with_suffix(".test.txt")
    final_test_srt_path = output_path.with_suffix(".test.srt")
    chapters_text_path = output_path.with_suffix(".chapters.txt")
    highlight_contract_path = output_path.with_suffix(".highlights.json")

    raw_test_text_path.write_text(_render_test_text_from_lines(raw_lines) + "\n", encoding="utf-8")
    final_test_text_path.write_text(_render_test_text_from_lines(polish_artifacts.lines) + "\n", encoding="utf-8")
    _write_srt(final_test_srt_path, build_subtitles_from_lines(polish_artifacts.lines), args.encoding)
    chapters_text_path.write_text(_render_chapters_text(chapter_artifacts.chapters) + "\n", encoding="utf-8")
    highlight_payload = _write_highlight_contract(
        highlight_contract_path,
        captions=_build_kept_captions_from_lines(polish_artifacts.lines),
        args=args,
    )
    payload = {
        "input_path": str(input_path),
        "raw_srt_path": str(raw_srt_path),
        "raw_test_text_path": str(raw_test_text_path),
        "final_test_text_path": str(final_test_text_path),
        "final_test_srt_path": str(final_test_srt_path),
        "chapters_text_path": str(chapters_text_path),
        "highlight_contract_path": str(highlight_contract_path),
        "review_report_path": str(review_report_path),
        "line_count": len(polish_artifacts.lines),
        "chapter_count": len(chapter_artifacts.chapters),
        "highlight_caption_count": len(list(highlight_payload.get("captions") or [])),
        "steps_debug": {
            "delete": delete_artifacts.debug,
            "polish": polish_artifacts.debug,
            "chapter": chapter_artifacts.debug,
            "highlight": {"captions": len(list(highlight_payload.get("captions") or []))},
            "review": review_meta,
        },
    }
    _write_json(output_path, payload)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the direct prompt subtitle pipeline tasks. The canonical main chain is delete -> polish; chapter/highlight are downstream sidecars.")
    parser.add_argument("--pi-bin", default="pi")
    parser.add_argument("--input", default=None)
    parser.add_argument("--task", choices=["delete", "polish", "chapter", "highlight", "test"], default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--llm-max-tokens", type=int, default=None)
    parser.add_argument("--title-max-chars", type=int, default=5)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--prompt", default="")
    parser.add_argument("pi_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def _run_cli_task(args: argparse.Namespace) -> int:
    if args.task == "test":
        return _run_cli_test(args)

    llm_config = _build_cli_llm_config(args)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if args.task == "delete":
        segments = _load_segments_from_path(input_path, args.encoding)
        artifacts = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines))
        output_path.write_text(_render_test_text_from_lines(artifacts.lines) + "\n", encoding="utf-8")
        return 0

    if args.task == "polish":
        if input_path.suffix.lower().endswith(".txt"):
            lines = _load_lines_from_test_text(input_path)
        else:
            segments = _load_segments_from_path(input_path, args.encoding)
            lines = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        artifacts = run_test_pi(TestPiRequest(task="polish", llm_config=llm_config, lines=lines, max_lines=args.max_lines))
        output_path.write_text(_render_test_text_from_lines(artifacts.lines) + "\n", encoding="utf-8")
        return 0

    if args.task == "highlight":
        if input_path.suffix.lower().endswith(".txt"):
            lines = _load_lines_from_test_text(input_path)
            captions = _build_kept_captions_from_lines(lines)
        elif input_path.suffix.lower() == ".srt":
            captions = [
                {
                    "index": int(sub.index),
                    "start": float(sub.start.total_seconds()),
                    "end": float(sub.end.total_seconds()),
                    "text": str(sub.content or "").strip(),
                }
                for sub in srt.parse(input_path.read_text(encoding=args.encoding))
                if str(sub.content or "").strip()
            ]
        else:
            segments = _load_segments_from_path(input_path, args.encoding)
            lines = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
            lines = run_test_pi(TestPiRequest(task="polish", llm_config=llm_config, lines=lines, max_lines=args.max_lines)).lines
            captions = _build_kept_captions_from_lines(lines)
        payload = request_subtitle_style_contract(
            captions=captions,
            llm_config=_build_cli_highlight_llm_config(args),
        )
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    if input_path.suffix.lower().endswith(".txt"):
        lines = _load_lines_from_test_text(input_path)
    else:
        segments = _load_segments_from_path(input_path, args.encoding)
        lines = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        lines = run_test_pi(TestPiRequest(task="polish", llm_config=llm_config, lines=lines, max_lines=args.max_lines)).lines
    artifacts = run_test_pi(
        TestPiRequest(task="chapter", llm_config=llm_config, lines=lines, title_max_chars=args.title_max_chars, max_lines=args.max_lines)
    )
    output_path.write_text(_render_chapters_text(artifacts.chapters) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.task:
        if not args.input or not args.output:
            raise RuntimeError("--input and --output are required when --task is used")
        return _run_cli_task(args)
    completed = subprocess.run(
        build_pi_command(pi_bin=args.pi_bin, pi_args=list(args.pi_args or [])),
        env=dict(os.environ),
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    return int(completed.returncode)
