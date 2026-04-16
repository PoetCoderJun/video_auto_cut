from __future__ import annotations

from pathlib import Path
from typing import Any

from video_auto_cut.editing.chapter_domain import ensure_full_block_coverage
from video_auto_cut.editing.llm_client import build_llm_config
from video_auto_cut.pi_agent_runner import TestPiRequest, run_test_pi

from .pipeline_options import build_pipeline_options
from ..utils.srt_utils import write_chapters_text


def generate_test_chapters(
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
    artifacts = run_test_pi(
        TestPiRequest(
            task="chapter",
            llm_config=llm_config,
            lines=kept_lines,
            title_max_chars=int(options.topic_title_max_chars),
        )
    )
    chapters = artifacts.chapters
    if not chapters:
        raise RuntimeError("test flow generated empty chapter list")
    ensure_full_block_coverage(chapters, total_blocks=len(kept_lines))
    write_chapters_text(chapters, output_path)
    return chapters
