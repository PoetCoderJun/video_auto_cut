from __future__ import annotations

import logging
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from video_auto_cut.orchestration.pipeline_service import (
    PipelineOptions,
    run_auto_edit,
    run_topic_segmentation_from_optimized_srt,
    run_transcribe,
)
from video_auto_cut.rendering.cut import Cutter
from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt
from video_auto_cut.shared import media as media_utils

from .artifacts import (
    STATUS_STEP1_CONFIRMED,
    STATUS_STEP1_READY,
    STATUS_STEP2_CONFIRMED,
    STATUS_STEP2_READY,
    STATUS_SUCCEEDED,
    HumanLoopPaths,
    copy_if_exists,
    ensure_full_line_coverage,
    ensure_paths,
    initialize_state,
    kept_line_ids,
    load_state,
    read_step1_lines,
    read_topics,
    save_state,
    stage_input_video,
    write_step1_json,
    write_step1_srt,
    write_topics_json,
)


def _update_status(paths: HumanLoopPaths, **updates: Any) -> dict[str, Any]:
    state = load_state(paths)
    state.update(updates)
    return save_state(paths, state)


def run_until_human_gate(
    *,
    input_video_path: Path,
    output_video_path: Path,
    artifact_root: str | None,
    options: PipelineOptions,
) -> dict[str, Any]:
    paths = ensure_paths(input_video_path, artifact_root)
    state = initialize_state(
        paths,
        input_video_path=input_video_path,
        output_video_path=output_video_path,
    )

    if state.get("status") == STATUS_STEP1_READY:
        logging.info("Step1 is waiting for human review: %s", paths.step1_draft_json)
        return state
    if state.get("status") == STATUS_STEP2_READY:
        logging.info("Step2 is waiting for human review: %s", paths.step2_draft_json)
        return state
    if state.get("status") == STATUS_SUCCEEDED:
        logging.info("Render already completed: %s", paths.render_output_path)
        return state

    staged_video = stage_input_video(input_video_path, paths)
    state = _update_status(paths, staged_video_path=str(staged_video))

    if not bool(state.get("step1_confirmed", False)):
        srt_path = run_transcribe(staged_video, options)
        optimized_srt_path = run_auto_edit(srt_path, options)
        sidecar_path = optimized_srt_path.with_suffix(".step1.json")
        if not sidecar_path.exists():
            raise RuntimeError(f"step1 sidecar missing: {sidecar_path}")

        copy_if_exists(srt_path, paths.step1_source_srt)
        copy_if_exists(optimized_srt_path, paths.step1_optimized_srt)
        copy_if_exists(sidecar_path, paths.step1_sidecar_json)

        lines = read_step1_lines(sidecar_path)
        write_step1_json(lines, paths.step1_draft_json)
        write_step1_srt(lines, paths.step1_draft_srt, options.encoding)
        return _update_status(
            paths,
            status=STATUS_STEP1_READY,
            step1_confirmed=False,
        )

    if not bool(state.get("step2_confirmed", False)):
        if not paths.step1_final_srt.exists():
            raise RuntimeError(f"missing confirmed step1 srt: {paths.step1_final_srt}")
        if not paths.step1_final_json.exists():
            raise RuntimeError(f"missing confirmed step1 json: {paths.step1_final_json}")

        run_topic_segmentation_from_optimized_srt(
            optimized_srt_path=paths.step1_final_srt,
            cut_srt_output_path=paths.step2_cut_srt,
            topics_output_path=paths.step2_topics_json,
            options=options,
        )

        lines = read_step1_lines(paths.step1_final_json)
        chapters = read_topics(paths.step2_topics_json)
        if not chapters:
            raise RuntimeError("step2 generated empty topics")
        ensure_full_line_coverage(chapters, kept_line_ids(lines))
        write_topics_json(chapters, paths.step2_draft_json)
        return _update_status(
            paths,
            status=STATUS_STEP2_READY,
            step2_confirmed=False,
        )

    logging.info("Both human gates are approved. Run render to export the final cut.")
    return state


def approve_step1(
    *,
    input_video_path: Path,
    artifact_root: str | None,
    review_json_path: Path | None,
    encoding: str,
) -> dict[str, Any]:
    paths = ensure_paths(input_video_path, artifact_root)
    state = load_state(paths)
    source_json = review_json_path or paths.step1_draft_json
    if not source_json.exists():
        raise RuntimeError(f"missing step1 review file: {source_json}")

    lines = read_step1_lines(source_json)
    if not lines:
        raise RuntimeError("step1 review payload is empty")
    write_step1_json(lines, paths.step1_final_json)
    write_step1_srt(lines, paths.step1_final_srt, encoding)
    return _update_status(
        paths,
        input_video_path=str(input_video_path),
        output_video_path=state.get("output_video_path"),
        status=STATUS_STEP1_CONFIRMED,
        step1_confirmed=True,
    )


def approve_step2(
    *,
    input_video_path: Path,
    artifact_root: str | None,
    review_json_path: Path | None,
) -> dict[str, Any]:
    paths = ensure_paths(input_video_path, artifact_root)
    state = load_state(paths)
    source_json = review_json_path or paths.step2_draft_json
    if not source_json.exists():
        raise RuntimeError(f"missing step2 review file: {source_json}")

    chapters = read_topics(source_json)
    if not chapters:
        raise RuntimeError("step2 review payload is empty")
    write_topics_json(chapters, paths.step2_final_json)
    return _update_status(
        paths,
        input_video_path=str(input_video_path),
        output_video_path=state.get("output_video_path"),
        status=STATUS_STEP2_CONFIRMED,
        step2_confirmed=True,
    )


def render_output(
    *,
    input_video_path: Path,
    artifact_root: str | None,
    options: PipelineOptions,
) -> dict[str, Any]:
    paths = ensure_paths(input_video_path, artifact_root)
    state = load_state(paths)
    if not bool(state.get("step1_confirmed", False)):
        raise RuntimeError("step1 must be approved before render")
    if not bool(state.get("step2_confirmed", False)):
        raise RuntimeError("step2 must be approved before render")
    if not paths.step1_final_srt.exists():
        raise RuntimeError(f"missing confirmed step1 srt: {paths.step1_final_srt}")

    build_cut_srt_from_optimized_srt(
        source_srt_path=str(paths.step1_final_srt),
        output_srt_path=str(paths.render_cut_srt),
        encoding=options.encoding,
        merge_gap_s=float(options.cut_merge_gap),
    )

    staged_video = Path(str(state.get("staged_video_path") or paths.staged_video_path))
    cutter_args = SimpleNamespace(
        inputs=[str(staged_video), str(paths.render_cut_srt)],
        force=bool(options.force),
        encoding=options.encoding,
        cut_merge_gap=float(options.cut_merge_gap),
    )
    Cutter(cutter_args).run()

    output_ext = "mp4" if media_utils.is_video(str(staged_video).lower()) else "mp3"
    generated_output = Path(media_utils.change_ext(media_utils.add_cut(str(staged_video)), output_ext))
    if not generated_output.exists():
        raise RuntimeError(f"render output missing: {generated_output}")

    paths.render_output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(generated_output), str(paths.render_output_path))

    requested_output = Path(str(state.get("output_video_path") or "")).expanduser()
    if requested_output:
        requested_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths.render_output_path, requested_output)

    return _update_status(paths, status=STATUS_SUCCEEDED)
