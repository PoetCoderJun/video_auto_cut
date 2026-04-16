from __future__ import annotations

import os
from typing import Any

from .pipeline_service import PipelineOptions


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _env_float(*names: str, default: float) -> float:
    raw = _env(*names)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _env_int(*names: str, default: int) -> int:
    raw = _env(*names)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _env_bool(*names: str, default: bool) -> bool:
    raw = _env(*names)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes"}


def _env_int_csv(*names: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = _env(*names)
    if raw is None:
        return default
    values: list[int] = []
    for item in str(raw).split(","):
        stripped = item.strip()
        if not stripped:
            continue
        try:
            values.append(int(stripped))
        except ValueError:
            continue
    return tuple(values) or default


def _build_common_values() -> dict[str, Any]:
    return {
        "encoding": "utf-8",
        "force": True,
        "lang": _env("DASHSCOPE_ASR_LANGUAGE", "ASR_DASHSCOPE_LANGUAGE", default="Chinese"),
        "prompt": "",
        "asr_backend": _env("ASR_BACKEND", default="dashscope_filetrans"),
        "asr_dashscope_base_url": _env(
            "DASHSCOPE_ASR_BASE_URL",
            "ASR_DASHSCOPE_BASE_URL",
            default=PipelineOptions.asr_dashscope_base_url,
        ),
        "asr_dashscope_model": _env(
            "DASHSCOPE_ASR_MODEL",
            "ASR_DASHSCOPE_MODEL",
            default=PipelineOptions.asr_dashscope_model,
        ),
        "asr_dashscope_task": _env("DASHSCOPE_ASR_TASK", "ASR_DASHSCOPE_TASK", default="") or "",
        "asr_dashscope_api_key": _env(
            "DASHSCOPE_ASR_API_KEY",
            "ASR_DASHSCOPE_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
        "asr_dashscope_poll_seconds": _env_float("DASHSCOPE_ASR_POLL_SECONDS", default=2.0),
        "asr_dashscope_timeout_seconds": _env_float("DASHSCOPE_ASR_TIMEOUT_SECONDS", default=3600.0),
        "asr_dashscope_language": _env("DASHSCOPE_ASR_LANGUAGE", "ASR_DASHSCOPE_LANGUAGE"),
        "asr_dashscope_language_hints": tuple(
            item.strip()
            for item in (_env("ASR_DASHSCOPE_LANGUAGE_HINTS", default="") or "").split(",")
            if item.strip()
        ),
        "asr_dashscope_context": _env("DASHSCOPE_ASR_TEXT", "ASR_DASHSCOPE_CONTEXT", default="") or "",
        "asr_dashscope_enable_itn": _env_bool("DASHSCOPE_ASR_ENABLE_ITN", default=False),
        "asr_dashscope_enable_words": _env_bool(
            "DASHSCOPE_ASR_ENABLE_WORDS",
            "ASR_DASHSCOPE_ENABLE_WORDS",
            default=True,
        ),
        "asr_dashscope_channel_ids": _env_int_csv("DASHSCOPE_ASR_CHANNEL_IDS", default=(0,)),
        "asr_dashscope_sentence_rule_with_punc": _env_bool(
            "ASR_SENTENCE_RULE_WITH_PUNC",
            "ASR_DASHSCOPE_SENTENCE_RULE_WITH_PUNC",
            default=True,
        ),
        "asr_dashscope_word_split_enabled": _env_bool(
            "ASR_WORD_SPLIT_ENABLED",
            "ASR_DASHSCOPE_WORD_SPLIT_ENABLED",
            default=True,
        ),
        "asr_dashscope_word_split_on_comma": _env_bool(
            "ASR_WORD_SPLIT_ON_COMMA",
            "ASR_DASHSCOPE_WORD_SPLIT_ON_COMMA",
            default=True,
        ),
        "asr_dashscope_word_split_comma_pause_s": _env_float(
            "ASR_WORD_SPLIT_COMMA_PAUSE_S",
            "ASR_DASHSCOPE_WORD_SPLIT_COMMA_PAUSE_S",
            default=0.4,
        ),
        "asr_dashscope_word_split_min_chars": _env_int(
            "ASR_WORD_SPLIT_MIN_CHARS",
            "ASR_DASHSCOPE_WORD_SPLIT_MIN_CHARS",
            default=12,
        ),
        "asr_dashscope_word_vad_gap_s": _env_float(
            "ASR_WORD_VAD_GAP_S",
            "ASR_DASHSCOPE_WORD_VAD_GAP_S",
            default=1.0,
        ),
        "asr_dashscope_word_max_segment_s": _env_float(
            "ASR_WORD_MAX_SEGMENT_S",
            "ASR_DASHSCOPE_WORD_MAX_SEGMENT_S",
            default=8.0,
        ),
        "asr_dashscope_no_speech_gap_s": _env_float(
            "ASR_NO_SPEECH_GAP_S",
            "ASR_DASHSCOPE_NO_SPEECH_GAP_S",
            default=1.0,
        ),
        "asr_dashscope_insert_no_speech": _env_bool(
            "ASR_INSERT_NO_SPEECH",
            "ASR_DASHSCOPE_INSERT_NO_SPEECH",
            default=True,
        ),
        "asr_dashscope_insert_head_no_speech": _env_bool(
            "ASR_INSERT_HEAD_NO_SPEECH",
            "ASR_DASHSCOPE_INSERT_HEAD_NO_SPEECH",
            default=True,
        ),
        "asr_oss_endpoint": _env("ASR_OSS_ENDPOINT"),
        "asr_oss_bucket": _env("ASR_OSS_BUCKET"),
        "asr_oss_access_key_id": _env("ASR_OSS_ACCESS_KEY_ID"),
        "asr_oss_access_key_secret": _env("ASR_OSS_ACCESS_KEY_SECRET"),
        "asr_oss_prefix": _env("ASR_OSS_PREFIX", default="video-auto-cut/asr") or "video-auto-cut/asr",
        "asr_oss_signed_url_ttl_seconds": _env_int("ASR_OSS_SIGNED_URL_TTL_SECONDS", default=86400),
        "llm_base_url": _env("LLM_BASE_URL"),
        "llm_model": _env("LLM_MODEL"),
        "topic_llm_model": _env("LLM_MODEL"),
        "llm_api_key": _env("LLM_API_KEY", "DASHSCOPE_API_KEY"),
        "llm_timeout": _env_int("LLM_TIMEOUT", default=300),
        "llm_temperature": _env_float("LLM_TEMPERATURE", default=0.2),
        "llm_max_tokens": None,
        "auto_edit_llm_concurrency": 4,
        "auto_edit_merge_gap": 0.5,
        "auto_edit_pad_head": 0.0,
        "auto_edit_pad_tail": 0.0,
        "cut_merge_gap": _env_float("CUT_MERGE_GAP", default=0.0),
        "topic_output": None,
        "topic_strict": False,
        "topic_max_topics": _env_int("TOPIC_MAX_TOPICS", default=5),
        "topic_title_max_chars": _env_int("TOPIC_TITLE_MAX_CHARS", default=6),
    }


def build_pipeline_options_from_env(**overrides: object) -> PipelineOptions:
    values = _build_common_values()
    values.update(overrides)
    return PipelineOptions(**values)


def build_pipeline_options_from_settings(settings: Any, **overrides: object) -> PipelineOptions:
    values = {
        "encoding": "utf-8",
        "force": True,
        "lang": settings.asr_dashscope_language or settings.lang,
        "prompt": "",
        "asr_backend": "dashscope_filetrans",
        "asr_dashscope_base_url": settings.asr_dashscope_base_url,
        "asr_dashscope_model": settings.asr_dashscope_model,
        "asr_dashscope_task": settings.asr_dashscope_task,
        "asr_dashscope_api_key": settings.asr_dashscope_api_key,
        "asr_dashscope_poll_seconds": settings.asr_dashscope_poll_seconds,
        "asr_dashscope_timeout_seconds": settings.asr_dashscope_timeout_seconds,
        "asr_dashscope_language": settings.asr_dashscope_language,
        "asr_dashscope_language_hints": settings.asr_dashscope_language_hints,
        "asr_dashscope_context": settings.asr_dashscope_context,
        "asr_dashscope_enable_itn": settings.asr_dashscope_enable_itn,
        "asr_dashscope_enable_words": settings.asr_dashscope_enable_words,
        "asr_dashscope_channel_ids": settings.asr_dashscope_channel_ids,
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
        "topic_llm_model": settings.llm_model,
        "llm_api_key": settings.llm_api_key,
        "llm_timeout": settings.llm_timeout,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "auto_edit_llm_concurrency": getattr(settings, "auto_edit_llm_concurrency", 4),
        "auto_edit_merge_gap": 0.5,
        "auto_edit_pad_head": 0.0,
        "auto_edit_pad_tail": 0.0,
        "cut_merge_gap": settings.cut_merge_gap,
        "topic_output": None,
        "topic_strict": False,
        "topic_max_topics": min(6, settings.topic_max_topics),
        "topic_title_max_chars": settings.topic_title_max_chars,
    }
    values.update(overrides)
    return PipelineOptions(**values)
