from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional


@dataclass(frozen=True)
class PipelineOptions:
    encoding: str = "utf-8"
    force: bool = False

    lang: str = "Chinese"
    prompt: str = ""

    asr_backend: str = "dashscope_filetrans"
    asr_dashscope_base_url: str = "https://dashscope.aliyuncs.com"
    asr_dashscope_model: str = "qwen3-asr-flash-filetrans"
    asr_dashscope_task: str = ""
    asr_dashscope_api_key: str | None = None
    asr_dashscope_poll_seconds: float = 2.0
    asr_dashscope_timeout_seconds: float = 3600.0
    asr_dashscope_language_hints: tuple[str, ...] = ()
    asr_dashscope_context: str = ""
    asr_dashscope_enable_words: bool = True
    asr_dashscope_sentence_rule_with_punc: bool = True
    asr_dashscope_word_split_enabled: bool = True
    asr_dashscope_word_split_on_comma: bool = True
    asr_dashscope_word_split_comma_pause_s: float = 0.4
    asr_dashscope_word_split_min_chars: int = 12
    asr_dashscope_word_vad_gap_s: float = 1.0
    asr_dashscope_word_max_segment_s: float = 8.0
    asr_dashscope_no_speech_gap_s: float = 1.0
    asr_dashscope_insert_no_speech: bool = True
    asr_dashscope_insert_head_no_speech: bool = True
    asr_oss_endpoint: str | None = None
    asr_oss_bucket: str | None = None
    asr_oss_access_key_id: str | None = None
    asr_oss_access_key_secret: str | None = None
    asr_oss_prefix: str = "video-auto-cut/asr"
    asr_oss_signed_url_ttl_seconds: int = 86400

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout: int = 300
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8192

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
    topic_title_max_chars: int = 6
    topic_summary_max_chars: int = 6
    topic_generate_summary: bool = True


RenderProgressCallback = Callable[[str, Optional[float]], None]
ASRProgressCallback = Callable[[float], None]


def require_llm(options: PipelineOptions, stage_name: str) -> None:
    if not options.llm_base_url or not options.llm_model:
        raise RuntimeError(
            f"{stage_name} requires LLM config: llm_base_url and llm_model."
        )


def build_transcribe_args(
    video_path: Path, options: PipelineOptions, *, oss_object_key: str | None = None
) -> SimpleNamespace:
    ns = SimpleNamespace(
        inputs=[str(video_path)],
        force=bool(options.force),
        encoding=options.encoding,
        transcribe=True,
        asr_backend=options.asr_backend,
        asr_dashscope_base_url=options.asr_dashscope_base_url,
        asr_dashscope_model=options.asr_dashscope_model,
        asr_dashscope_task=options.asr_dashscope_task,
        asr_dashscope_api_key=options.asr_dashscope_api_key,
        asr_dashscope_poll_seconds=float(options.asr_dashscope_poll_seconds),
        asr_dashscope_timeout_seconds=float(options.asr_dashscope_timeout_seconds),
        asr_dashscope_language_hints=list(options.asr_dashscope_language_hints),
        asr_dashscope_context=options.asr_dashscope_context,
        asr_dashscope_enable_words=bool(options.asr_dashscope_enable_words),
        asr_dashscope_sentence_rule_with_punc=bool(options.asr_dashscope_sentence_rule_with_punc),
        asr_dashscope_word_split_enabled=bool(options.asr_dashscope_word_split_enabled),
        asr_dashscope_word_split_on_comma=bool(options.asr_dashscope_word_split_on_comma),
        asr_dashscope_word_split_comma_pause_s=float(options.asr_dashscope_word_split_comma_pause_s),
        asr_dashscope_word_split_min_chars=int(options.asr_dashscope_word_split_min_chars),
        asr_dashscope_word_vad_gap_s=float(options.asr_dashscope_word_vad_gap_s),
        asr_dashscope_word_max_segment_s=float(options.asr_dashscope_word_max_segment_s),
        asr_dashscope_no_speech_gap_s=float(options.asr_dashscope_no_speech_gap_s),
        asr_dashscope_insert_no_speech=bool(options.asr_dashscope_insert_no_speech),
        asr_dashscope_insert_head_no_speech=bool(options.asr_dashscope_insert_head_no_speech),
        asr_oss_endpoint=options.asr_oss_endpoint,
        asr_oss_bucket=options.asr_oss_bucket,
        asr_oss_access_key_id=options.asr_oss_access_key_id,
        asr_oss_access_key_secret=options.asr_oss_access_key_secret,
        asr_oss_prefix=options.asr_oss_prefix,
        asr_oss_signed_url_ttl_seconds=int(options.asr_oss_signed_url_ttl_seconds),
        llm_base_url=options.llm_base_url,
        llm_model=options.llm_model,
        llm_api_key=options.llm_api_key,
        llm_timeout=int(options.llm_timeout),
        llm_temperature=float(options.llm_temperature),
        llm_max_tokens=int(options.llm_max_tokens),
        lang=options.lang,
        prompt=options.prompt,
    )
    if oss_object_key:
        setattr(ns, "oss_object_key", oss_object_key)
    return ns


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
        topic_title_max_chars=int(options.topic_title_max_chars),
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
        topic_title_max_chars=int(options.topic_title_max_chars),
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
        topic_title_max_chars=int(options.topic_title_max_chars),
        topic_summary_max_chars=int(options.topic_summary_max_chars),
        topic_generate_summary=bool(options.topic_generate_summary),
        llm_base_url=options.llm_base_url,
        llm_model=options.llm_model,
        llm_api_key=options.llm_api_key,
        llm_timeout=int(options.llm_timeout),
        llm_temperature=float(options.llm_temperature),
        llm_max_tokens=int(options.llm_max_tokens),
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
    args = build_transcribe_args(video_path, options, oss_object_key=oss_object_key)
    if progress_callback is not None:
        setattr(args, "asr_progress_callback", progress_callback)
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


def run_render(
    video_path: Path,
    optimized_srt_path: Path,
    options: PipelineOptions,
    *,
    progress_callback: RenderProgressCallback | None = None,
) -> None:
    from video_auto_cut.rendering.remotion_renderer import RemotionRenderer

    if options.render_topics and not options.render_topics_input:
        require_llm(options, "Render topic segmentation")
    logging.info("Step 3/3: remotion render")
    args = build_render_args(video_path, optimized_srt_path, options)
    if progress_callback is not None:
        setattr(args, "render_progress_callback", progress_callback)
    RemotionRenderer(args).run()


def warm_render_cut_cache(
    video_path: Path,
    optimized_srt_path: Path,
    options: PipelineOptions,
    *,
    progress_callback: RenderProgressCallback | None = None,
) -> str:
    from video_auto_cut.rendering.remotion_renderer import RemotionRenderer

    args = build_render_args(video_path, optimized_srt_path, options)
    if progress_callback is not None:
        setattr(args, "render_progress_callback", progress_callback)
    renderer = RemotionRenderer(args)
    return renderer.warmup_cut_video()
