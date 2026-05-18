from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from video_auto_cut.shared.interfaces import PipelineOptions

@dataclass(frozen=True)
class AutoEditArtifacts:
    optimized_srt_path: Path
    test_lines: list[dict[str, Any]]
    test_text_path: Path


RenderProgressCallback = Callable[[str, Optional[float]], None]
ASRProgressCallback = Callable[[float], None]
AutoEditStageCallback = Callable[[str, str], None]
AutoEditPreviewCallback = Callable[[list[dict[str, Any]]], None]


def require_llm(options: PipelineOptions, stage_name: str) -> None:
    if not options.llm_base_url or not options.llm_model:
        raise RuntimeError(
            f"{stage_name} requires LLM config: llm_base_url and llm_model."
        )


def run_transcribe(
    video_path: Path,
    options: PipelineOptions,
    *,
    progress_callback: ASRProgressCallback | None = None,
    oss_object_key: str | None = None,
) -> Path:
    from video_auto_cut.asr.transcribe import Transcribe

    asr_backend = (options.asr_backend or "").strip().lower() or "dashscope_filetrans"
    if asr_backend != "dashscope_filetrans":
        raise RuntimeError(
            f"Unsupported ASR backend for web deployment: {asr_backend}. "
            "Only dashscope_filetrans is supported."
        )
    logging.info("Step 1/3: transcribe -> SRT")
    Transcribe(
        video_path,
        options,
        oss_object_key=oss_object_key,
        progress_callback=progress_callback,
    ).run()

    srt_path = video_path.with_suffix(".srt")
    if not srt_path.exists():
        raise RuntimeError(f"Transcribe step did not produce SRT: {srt_path}")
    return srt_path


def run_auto_edit(
    srt_path: Path,
    options: PipelineOptions,
    *,
    stage_callback: AutoEditStageCallback | None = None,
    preview_callback: AutoEditPreviewCallback | None = None,
) -> AutoEditArtifacts:
    from video_auto_cut.editing.auto_edit import AutoEdit

    require_llm(options, "Auto-edit")
    logging.info("Step 2/3: auto edit -> optimized SRT")
    editor = AutoEdit.from_pipeline_options(
        srt_path,
        options,
        stage_callback=stage_callback,
        preview_callback=preview_callback,
    )
    editor.run()

    optimized = srt_path.with_name(f"{srt_path.stem}.optimized.srt")
    if not optimized.exists():
        raise RuntimeError(f"Auto-edit step did not produce optimized SRT: {optimized}")
    if editor.last_result is None:
        raise RuntimeError("Auto-edit step did not expose canonical test lines.")
    return AutoEditArtifacts(
        optimized_srt_path=optimized,
        test_lines=list(editor.last_result.get("test_lines") or []),
        test_text_path=Path(str(editor.last_result.get("test_text_path") or optimized.with_suffix(".test.txt"))),
    )
