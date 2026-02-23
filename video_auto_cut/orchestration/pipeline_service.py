from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


@dataclass(frozen=True)
class PipelineOptions:
    encoding: str = "utf-8"
    force: bool = False

    device: str = "cpu"
    lang: str = "Chinese"
    prompt: str = ""

    qwen3_model: str = "./model/Qwen3-ASR-0.6B"
    qwen3_aligner: str = "./model/Qwen3-ForcedAligner-0.6B"
    qwen3_language: str | None = None
    qwen3_use_modelscope: bool = False
    qwen3_offline: bool = True
    qwen3_gap: float = 0.6
    qwen3_max_seg: float = 20.0
    qwen3_max_chars: int = 0
    qwen3_no_speech_gap: float = 1.0
    qwen3_use_punct: bool = True

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout: int = 60
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096

    auto_edit_merge_gap: float = 0.5
    auto_edit_pad_head: float = 0.0
    auto_edit_pad_tail: float = 0.0

    bitrate: str = "10m"
    cut_merge_gap: float = 0.0
    render_output: str | None = None
    render_cut_srt_output: str | None = None
    render_fps: float | None = None
    render_preview: bool = False
    render_codec: str | None = None
    render_crf: int | None = None
    render_topics: bool = True
    render_topics_input: str | None = None

    topic_output: str | None = None
    topic_strict: bool = False
    topic_max_topics: int = 8
    topic_summary_max_chars: int = 6


def require_llm(options: PipelineOptions, stage_name: str) -> None:
    if not options.llm_base_url or not options.llm_model:
        raise RuntimeError(
            f"{stage_name} requires LLM config: llm_base_url and llm_model."
        )


def build_transcribe_args(video_path: Path, options: PipelineOptions) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(video_path)],
        force=bool(options.force),
        encoding=options.encoding,
        transcribe=True,
        qwen3_model=options.qwen3_model,
        qwen3_aligner=options.qwen3_aligner,
        qwen3_language=options.qwen3_language,
        qwen3_use_modelscope=bool(options.qwen3_use_modelscope),
        qwen3_offline=bool(options.qwen3_offline),
        qwen3_gap=float(options.qwen3_gap),
        qwen3_max_seg=float(options.qwen3_max_seg),
        qwen3_max_chars=int(options.qwen3_max_chars),
        qwen3_no_speech_gap=float(options.qwen3_no_speech_gap),
        qwen3_use_punct=bool(options.qwen3_use_punct),
        device=options.device,
        lang=options.lang,
        prompt=options.prompt,
    )


def build_auto_edit_args(srt_path: Path, options: PipelineOptions) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(srt_path)],
        force=bool(options.force),
        encoding=options.encoding,
        auto_edit=True,
        auto_edit_llm=True,
        auto_edit_merge_gap=float(options.auto_edit_merge_gap),
        auto_edit_pad_head=float(options.auto_edit_pad_head),
        auto_edit_pad_tail=float(options.auto_edit_pad_tail),
        auto_edit_output=None,
        auto_edit_topics=False,
        llm_base_url=options.llm_base_url,
        llm_model=options.llm_model,
        llm_api_key=options.llm_api_key,
        llm_timeout=int(options.llm_timeout),
        llm_temperature=float(options.llm_temperature),
        llm_max_tokens=int(options.llm_max_tokens),
        topic_output=None,
        topic_strict=bool(options.topic_strict),
        topic_max_topics=int(options.topic_max_topics),
        topic_summary_max_chars=int(options.topic_summary_max_chars),
    )


def build_render_args(
    video_path: Path, optimized_srt_path: Path, options: PipelineOptions
) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(video_path), str(optimized_srt_path)],
        encoding=options.encoding,
        bitrate=options.bitrate,
        cut_merge_gap=float(options.cut_merge_gap),
        render=True,
        render_output=options.render_output,
        render_cut_srt_output=options.render_cut_srt_output,
        render_topics=bool(options.render_topics),
        render_topics_input=options.render_topics_input,
        render_fps=options.render_fps,
        render_preview=bool(options.render_preview),
        render_codec=options.render_codec,
        render_crf=options.render_crf,
        topic_output=options.topic_output,
        topic_strict=bool(options.topic_strict),
        topic_max_topics=int(options.topic_max_topics),
        topic_summary_max_chars=int(options.topic_summary_max_chars),
        llm_base_url=options.llm_base_url,
        llm_model=options.llm_model,
        llm_api_key=options.llm_api_key,
        llm_timeout=int(options.llm_timeout),
        llm_temperature=float(options.llm_temperature),
        llm_max_tokens=int(options.llm_max_tokens),
    )


def build_topic_args(
    srt_path: Path, output_path: Path, options: PipelineOptions
) -> SimpleNamespace:
    return SimpleNamespace(
        inputs=[str(srt_path)],
        encoding=options.encoding,
        topic_output=str(output_path),
        topic_strict=bool(options.topic_strict),
        topic_max_topics=int(options.topic_max_topics),
        topic_summary_max_chars=int(options.topic_summary_max_chars),
        llm_base_url=options.llm_base_url,
        llm_model=options.llm_model,
        llm_api_key=options.llm_api_key,
        llm_timeout=int(options.llm_timeout),
        llm_temperature=float(options.llm_temperature),
        llm_max_tokens=int(options.llm_max_tokens),
    )


def run_transcribe(video_path: Path, options: PipelineOptions) -> Path:
    from video_auto_cut.asr.transcribe import Transcribe

    logging.info("Step 1/3: transcribe -> SRT")
    args = build_transcribe_args(video_path, options)
    Transcribe(args).run()

    srt_path = video_path.with_suffix(".srt")
    if not srt_path.exists():
        raise RuntimeError(f"Transcribe step did not produce SRT: {srt_path}")
    return srt_path


def run_auto_edit(srt_path: Path, options: PipelineOptions) -> Path:
    from video_auto_cut.editing.auto_edit import AutoEdit

    require_llm(options, "Auto-edit")
    logging.info("Step 2/3: auto edit -> optimized SRT")
    args = build_auto_edit_args(srt_path, options)
    AutoEdit(args).run()

    optimized = srt_path.with_name(f"{srt_path.stem}.optimized.srt")
    if not optimized.exists():
        raise RuntimeError(f"Auto-edit step did not produce optimized SRT: {optimized}")
    return optimized


def run_topic_segmentation_from_optimized_srt(
    optimized_srt_path: Path,
    cut_srt_output_path: Path,
    topics_output_path: Path,
    options: PipelineOptions,
) -> Path:
    from video_auto_cut.editing.topic_segment import TopicSegmenter
    from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt

    require_llm(options, "Topic segmentation")
    build_cut_srt_from_optimized_srt(
        source_srt_path=str(optimized_srt_path),
        output_srt_path=str(cut_srt_output_path),
        encoding=options.encoding,
        merge_gap_s=float(options.cut_merge_gap),
    )

    topic_args = build_topic_args(cut_srt_output_path, topics_output_path, options)
    segmenter = TopicSegmenter(topic_args)
    segmenter.run_for_srt(str(cut_srt_output_path), output_path=str(topics_output_path))

    if not topics_output_path.exists():
        raise RuntimeError(f"Topic segmentation did not produce output: {topics_output_path}")
    return topics_output_path


def run_render(video_path: Path, optimized_srt_path: Path, options: PipelineOptions) -> None:
    from video_auto_cut.rendering.remotion_renderer import RemotionRenderer

    if options.render_topics and not options.render_topics_input:
        require_llm(options, "Render topic segmentation")
    logging.info("Step 3/3: remotion render")
    args = build_render_args(video_path, optimized_srt_path, options)
    RemotionRenderer(args).run()
