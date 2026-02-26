from __future__ import annotations

from video_auto_cut.orchestration.pipeline_service import PipelineOptions

from ..config import get_settings
from ..constants import DEFAULT_ENCODING


def build_pipeline_options(**overrides: object) -> PipelineOptions:
    settings = get_settings()
    values = {
        "encoding": DEFAULT_ENCODING,
        "force": True,
        "lang": settings.lang,
        "prompt": "",
        "asr_backend": "dashscope_filetrans",
        "asr_dashscope_base_url": settings.asr_dashscope_base_url,
        "asr_dashscope_model": settings.asr_dashscope_model,
        "asr_dashscope_task": settings.asr_dashscope_task,
        "asr_dashscope_api_key": settings.asr_dashscope_api_key,
        "asr_dashscope_poll_seconds": settings.asr_dashscope_poll_seconds,
        "asr_dashscope_timeout_seconds": settings.asr_dashscope_timeout_seconds,
        "asr_dashscope_language_hints": settings.asr_dashscope_language_hints,
        "asr_dashscope_context": settings.asr_dashscope_context,
        "asr_dashscope_enable_words": settings.asr_dashscope_enable_words,
        "asr_dashscope_sentence_rule_with_punc": settings.asr_dashscope_sentence_rule_with_punc,
        "asr_dashscope_word_split_enabled": settings.asr_dashscope_word_split_enabled,
        "asr_dashscope_word_split_on_comma": settings.asr_dashscope_word_split_on_comma,
        "asr_dashscope_word_split_comma_pause_s": settings.asr_dashscope_word_split_comma_pause_s,
        "asr_dashscope_word_split_min_chars": settings.asr_dashscope_word_split_min_chars,
        "asr_dashscope_word_vad_gap_s": settings.asr_dashscope_word_vad_gap_s,
        "asr_dashscope_word_max_segment_s": settings.asr_dashscope_word_max_segment_s,
        "asr_dashscope_no_speech_gap_s": settings.asr_dashscope_no_speech_gap_s,
        "asr_dashscope_insert_no_speech": settings.asr_dashscope_insert_no_speech,
        "asr_dashscope_insert_head_no_speech": settings.asr_dashscope_insert_head_no_speech,
        "asr_oss_endpoint": settings.asr_oss_endpoint,
        "asr_oss_bucket": settings.asr_oss_bucket,
        "asr_oss_access_key_id": settings.asr_oss_access_key_id,
        "asr_oss_access_key_secret": settings.asr_oss_access_key_secret,
        "asr_oss_prefix": settings.asr_oss_prefix,
        "asr_oss_signed_url_ttl_seconds": settings.asr_oss_signed_url_ttl_seconds,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_api_key": settings.llm_api_key,
        "llm_timeout": settings.llm_timeout,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "auto_edit_merge_gap": 0.5,
        "auto_edit_pad_head": 0.0,
        "auto_edit_pad_tail": 0.0,
        "cut_merge_gap": settings.cut_merge_gap,
        "render_output": None,
        "render_cut_srt_output": None,
        "render_fps": None,
        "render_preview": False,
        "render_codec": None,
        "render_crf": None,
        "render_topics": False,
        "render_topics_input": None,
        "topic_output": None,
        "topic_strict": False,
        "topic_max_topics": settings.topic_max_topics,
        "topic_title_max_chars": settings.topic_title_max_chars,
        "topic_summary_max_chars": settings.topic_summary_max_chars,
        "topic_generate_summary": False,
    }
    values.update(overrides)
    return PipelineOptions(**values)
