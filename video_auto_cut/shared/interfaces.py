from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineOptions:
    encoding: str = "utf-8"
    force: bool = False

    lang: str = "Chinese"
    prompt: str = ""

    asr_backend: str = "dashscope_filetrans"
    asr_dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com"
    asr_dashscope_model: str = "qwen3-asr-flash-filetrans"
    asr_dashscope_task: str = ""
    asr_dashscope_api_key: str | None = None
    asr_dashscope_poll_seconds: float = 2.0
    asr_dashscope_timeout_seconds: float = 3600.0
    asr_dashscope_language: str | None = None
    asr_dashscope_language_hints: tuple[str, ...] = ()
    asr_dashscope_context: str = ""
    asr_dashscope_enable_itn: bool = False
    asr_dashscope_enable_words: bool = True
    asr_dashscope_channel_ids: tuple[int, ...] = (0,)
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
    topic_llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout: int = 300
    llm_temperature: float = 0.2
    llm_max_tokens: int | None = None
    auto_edit_llm_concurrency: int = 4

    auto_edit_merge_gap: float = 0.5
    auto_edit_pad_head: float = 0.0
    auto_edit_pad_tail: float = 0.0

    bitrate: str = "10m"
    cut_merge_gap: float = 0.0

    topic_output: str | None = None
    topic_strict: bool = False
    topic_max_topics: int = 5
    topic_title_max_chars: int = 6
