from __future__ import annotations

from dataclasses import fields
import os
from typing import Any

from video_auto_cut.shared.interfaces import PipelineOptions


PIPELINE_OPTION_FIELD_NAMES = tuple(field.name for field in fields(PipelineOptions))


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


def _env_optional_int(*names: str) -> int | None:
    raw = _env(*names)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


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
        "lang": _env(
            "WEB_LANG",
            "DASHSCOPE_ASR_LANGUAGE",
            default="Chinese",
        ),
        "prompt": "",
        "asr_backend": _env("ASR_BACKEND", default="dashscope_filetrans"),
        "asr_dashscope_base_url": _env(
            "DASHSCOPE_ASR_BASE_URL",
            default=PipelineOptions.asr_dashscope_base_url,
        ),
        "asr_dashscope_model": _env(
            "DASHSCOPE_ASR_MODEL",
            default=PipelineOptions.asr_dashscope_model,
        ),
        "asr_dashscope_task": _env("DASHSCOPE_ASR_TASK", default="") or "",
        "asr_dashscope_api_key": _env(
            "DASHSCOPE_ASR_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
        "asr_dashscope_poll_seconds": _env_float(
            "DASHSCOPE_ASR_POLL_SECONDS",
            default=2.0,
        ),
        "asr_dashscope_timeout_seconds": _env_float(
            "DASHSCOPE_ASR_TIMEOUT_SECONDS",
            default=3600.0,
        ),
        "asr_dashscope_language": _env("DASHSCOPE_ASR_LANGUAGE"),
        "asr_dashscope_language_hints": tuple(
            item.strip()
            for item in (
                _env(
                    "DASHSCOPE_ASR_LANGUAGE_HINTS",
                    default="",
                )
                or ""
            ).split(",")
            if item.strip()
        ),
        "asr_dashscope_context": _env("DASHSCOPE_ASR_TEXT", default="") or "",
        "asr_dashscope_enable_itn": _env_bool("DASHSCOPE_ASR_ENABLE_ITN", default=False),
        "asr_dashscope_enable_words": _env_bool(
            "DASHSCOPE_ASR_ENABLE_WORDS",
            default=True,
        ),
        "asr_dashscope_channel_ids": _env_int_csv(
            "DASHSCOPE_ASR_CHANNEL_IDS",
            default=(0,),
        ),
        "asr_dashscope_sentence_rule_with_punc": _env_bool(
            "ASR_SENTENCE_RULE_WITH_PUNC",
            default=True,
        ),
        "asr_dashscope_word_split_enabled": _env_bool(
            "ASR_WORD_SPLIT_ENABLED",
            default=True,
        ),
        "asr_dashscope_word_split_on_comma": _env_bool(
            "ASR_WORD_SPLIT_ON_COMMA",
            default=True,
        ),
        "asr_dashscope_word_split_comma_pause_s": _env_float(
            "ASR_WORD_SPLIT_COMMA_PAUSE_S",
            default=0.4,
        ),
        "asr_dashscope_word_split_min_chars": _env_int(
            "ASR_WORD_SPLIT_MIN_CHARS",
            default=12,
        ),
        "asr_dashscope_word_vad_gap_s": _env_float(
            "ASR_WORD_VAD_GAP_S",
            default=1.0,
        ),
        "asr_dashscope_word_max_segment_s": _env_float(
            "ASR_WORD_MAX_SEGMENT_S",
            default=8.0,
        ),
        "asr_dashscope_no_speech_gap_s": _env_float(
            "ASR_NO_SPEECH_GAP_S",
            default=1.0,
        ),
        "asr_dashscope_insert_no_speech": _env_bool(
            "ASR_INSERT_NO_SPEECH",
            default=True,
        ),
        "asr_dashscope_insert_head_no_speech": _env_bool(
            "ASR_INSERT_HEAD_NO_SPEECH",
            default=True,
        ),
        "asr_oss_endpoint": _env("ASR_OSS_ENDPOINT"),
        "asr_oss_bucket": _env("ASR_OSS_BUCKET"),
        "asr_oss_access_key_id": _env("ASR_OSS_ACCESS_KEY_ID"),
        "asr_oss_access_key_secret": _env("ASR_OSS_ACCESS_KEY_SECRET"),
        "asr_oss_prefix": _env(
            "ASR_OSS_PREFIX",
            default="video-auto-cut/asr",
        )
        or "video-auto-cut/asr",
        "asr_oss_signed_url_ttl_seconds": _env_int(
            "ASR_OSS_SIGNED_URL_TTL_SECONDS",
            default=86400,
        ),
        "llm_base_url": _env("LLM_BASE_URL"),
        "llm_model": _env("LLM_MODEL"),
        "topic_llm_model": _env("TOPIC_LLM_MODEL", "LLM_MODEL"),
        "llm_api_key": _env("LLM_API_KEY", "DASHSCOPE_API_KEY"),
        "llm_timeout": _env_int("LLM_TIMEOUT", default=300),
        "llm_temperature": _env_float("LLM_TEMPERATURE", default=0.2),
        "llm_max_tokens": _env_optional_int("LLM_MAX_TOKENS"),
        "auto_edit_llm_concurrency": _env_int("AUTO_EDIT_LLM_CONCURRENCY", default=4),
        "auto_edit_merge_gap": 0.5,
        "auto_edit_pad_head": 0.0,
        "auto_edit_pad_tail": 0.0,
        "cut_merge_gap": _env_float("CUT_MERGE_GAP", default=0.0),
        "topic_output": None,
        "topic_strict": False,
        "topic_max_topics": _env_int("TOPIC_MAX_TOPICS", default=5),
        "topic_title_max_chars": _env_int("TOPIC_TITLE_MAX_CHARS", default=6),
    }


def build_pipeline_values_from_env(**overrides: object) -> dict[str, Any]:
    values = _build_common_values()
    values.update(overrides)
    return values


def build_pipeline_options_from_env(**overrides: object) -> PipelineOptions:
    return PipelineOptions(**build_pipeline_values_from_env(**overrides))


def build_pipeline_option_values_from_source(source: Any) -> dict[str, Any]:
    return {
        name: getattr(source, name)
        for name in PIPELINE_OPTION_FIELD_NAMES
        if hasattr(source, name)
    }


def build_pipeline_options_from_settings(settings: Any, **overrides: object) -> PipelineOptions:
    values = build_pipeline_option_values_from_source(settings)
    values.update(
        {
            "encoding": "utf-8",
            "force": True,
            "lang": settings.asr_dashscope_language or settings.lang,
            "prompt": "",
            "asr_backend": "dashscope_filetrans",
            "topic_llm_model": settings.llm_model,
            "auto_edit_merge_gap": 0.5,
            "auto_edit_pad_head": 0.0,
            "auto_edit_pad_tail": 0.0,
            "topic_output": None,
            "topic_strict": False,
            "topic_max_topics": min(6, settings.topic_max_topics),
        }
    )
    values.update(overrides)
    return PipelineOptions(**values)
