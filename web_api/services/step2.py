from __future__ import annotations

from pathlib import Path
from typing import Any

from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_step1_chapters,
    ensure_full_block_coverage,
    kept_step1_lines,
)
from video_auto_cut.editing.llm_client import build_llm_config
from video_auto_cut.pi_agent_runner import Step1PiRequest, run_step1_pi

from .pipeline_options import build_pipeline_options
from ..utils.srt_utils import write_topics_json


def generate_step1_chapters(
    *,
    source_srt: Path,
    output_path: Path,
    kept_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    _ = source_srt
    options = build_pipeline_options()
    llm_config = build_llm_config(
        base_url=options.llm_base_url,
        model=options.llm_model,
        api_key=options.llm_api_key,
        timeout=options.llm_timeout,
        temperature=0.0,
        max_tokens=options.llm_max_tokens,
        enable_thinking=False,
    )
    artifacts = run_step1_pi(
        Step1PiRequest(
            task="chapter",
            llm_config=llm_config,
            lines=kept_lines,
            title_max_chars=int(options.topic_title_max_chars),
        )
    )
    chapters = artifacts.chapters
    if not chapters:
        raise RuntimeError("step1 generated empty chapter list")
    ensure_full_block_coverage(chapters, total_blocks=len(kept_lines))
    write_topics_json(chapters, output_path)
    return chapters
