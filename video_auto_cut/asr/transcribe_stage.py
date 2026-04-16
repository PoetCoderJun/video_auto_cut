from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from video_auto_cut.orchestration.pipeline_service import (
    ASRProgressCallback,
    PipelineOptions,
    run_transcribe,
)
from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_env
from web_api.utils.srt_utils import build_test_lines_from_srt, write_test_text


@dataclass(frozen=True)
class ASRTranscriptionArtifacts:
    media_path: Path
    srt_path: Path
    test_lines: list[dict[str, Any]]
    test_text_path: Path | None = None

def write_test_lines_text(lines: list[dict[str, Any]], output_path: Path) -> None:
    write_test_text(lines, output_path)


def write_test_lines_json(lines: list[dict[str, Any]], output_path: Path, *, encoding: str = "utf-8") -> None:
    payload = {"lines": lines}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding=encoding)


def run_asr_transcription_stage(
    media_path: Path,
    options: PipelineOptions,
    *,
    progress_callback: ASRProgressCallback | None = None,
    oss_object_key: str | None = None,
    write_test_text_sidecar: bool = False,
    test_text_output_path: Path | None = None,
) -> ASRTranscriptionArtifacts:
    normalized_media_path = Path(media_path).expanduser()
    srt_path = run_transcribe(
        normalized_media_path,
        options,
        progress_callback=progress_callback,
        oss_object_key=oss_object_key,
    )
    test_lines = build_test_lines_from_srt(srt_path, options.encoding)
    test_text_path: Path | None = None
    if write_test_text_sidecar:
        test_text_path = (
            Path(test_text_output_path).expanduser()
            if test_text_output_path is not None
            else srt_path.with_suffix(".test.txt")
        )
        write_test_lines_text(test_lines, test_text_path)
    return ASRTranscriptionArtifacts(
        media_path=normalized_media_path,
        srt_path=srt_path,
        test_lines=test_lines,
        test_text_path=test_text_path,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the current ASR transcription flow and emit Test-ready artifacts."
    )
    parser.add_argument("--input", required=True, help="Local media file path")
    parser.add_argument(
        "--oss-object-key",
        default="",
        help="Existing OSS object key for direct-OSS transcription mode",
    )
    parser.add_argument("--lang", default=None, help="ASR language override")
    parser.add_argument("--prompt", default="", help="Optional ASR context / hint text")
    parser.add_argument(
        "--test-json-path",
        default="",
        help="Optional output path for Test lines JSON (default: <input>.test.json)",
    )
    parser.add_argument(
        "--skip-test-json",
        action="store_true",
        help="Only emit SRT and skip the Test lines JSON sidecar",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files if they already exist",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[asr-transcribe] %(message)s")

    media_path = Path(args.input).expanduser().resolve()
    options = build_pipeline_options_from_env(
        force=bool(args.force),
        lang=(args.lang or None),
        prompt=str(args.prompt or ""),
    )
    artifacts = run_asr_transcription_stage(
        media_path,
        options,
        oss_object_key=str(args.oss_object_key or "").strip() or None,
    )
    test_json_path: Path | None = None
    if not bool(args.skip_test_json):
        test_json_path = (
            Path(args.test_json_path).expanduser().resolve()
            if str(args.test_json_path or "").strip()
            else media_path.with_suffix(".test.json")
        )
        write_test_lines_json(artifacts.test_lines, test_json_path, encoding=options.encoding)

    payload = {
        "media_path": str(artifacts.media_path),
        "srt_path": str(artifacts.srt_path),
        "test_json_path": str(test_json_path) if test_json_path is not None else None,
        "line_count": len(artifacts.test_lines),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
