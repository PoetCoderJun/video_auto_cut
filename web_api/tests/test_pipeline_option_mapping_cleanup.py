from __future__ import annotations

import os
import unittest
from dataclasses import asdict, fields
from types import SimpleNamespace
from unittest.mock import patch

from video_auto_cut.orchestration.pipeline_options_builder import (
    build_pipeline_options_from_env,
    build_pipeline_options_from_settings,
)
from video_auto_cut.shared.interfaces import PipelineOptions
from web_api.config import Settings, get_settings


_PIPELINE_OPTION_FIELD_NAMES = {field.name for field in fields(PipelineOptions)}
_SETTINGS_PIPELINE_FIELD_NAMES = {
    field.name for field in fields(Settings) if field.name in _PIPELINE_OPTION_FIELD_NAMES
}


class PipelineOptionMappingCleanupTest(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_build_pipeline_options_from_settings_reflects_shared_fields(self) -> None:
        pipeline_values = asdict(
            PipelineOptions(
                encoding="gbk",
                force=False,
                lang="SettingsLang",
                prompt="ignored prompt",
                asr_backend="ignored-backend",
                asr_dashscope_base_url="https://example.invalid",
                asr_dashscope_model="asr-model",
                asr_dashscope_task="task",
                asr_dashscope_api_key="asr-key",
                asr_dashscope_poll_seconds=3.5,
                asr_dashscope_timeout_seconds=1234.0,
                asr_dashscope_language="zh",
                asr_dashscope_language_hints=("zh", "en"),
                asr_dashscope_context="ctx",
                asr_dashscope_enable_itn=True,
                asr_dashscope_enable_words=False,
                asr_dashscope_channel_ids=(2, 3),
                asr_dashscope_sentence_rule_with_punc=False,
                asr_dashscope_word_split_enabled=False,
                asr_dashscope_word_split_on_comma=False,
                asr_dashscope_word_split_comma_pause_s=0.7,
                asr_dashscope_word_split_min_chars=21,
                asr_dashscope_word_vad_gap_s=1.7,
                asr_dashscope_word_max_segment_s=12.0,
                asr_dashscope_no_speech_gap_s=2.3,
                asr_dashscope_insert_no_speech=False,
                asr_dashscope_insert_head_no_speech=False,
                asr_oss_endpoint="https://oss.example.invalid",
                asr_oss_bucket="bucket",
                asr_oss_access_key_id="ak",
                asr_oss_access_key_secret="sk",
                asr_oss_prefix="prefix",
                asr_oss_signed_url_ttl_seconds=321,
                llm_base_url="https://llm.example.invalid",
                llm_model="main-model",
                topic_llm_model="topic-only-model",
                llm_api_key="llm-key",
                llm_timeout=456,
                llm_temperature=0.6,
                llm_max_tokens=789,
                auto_edit_llm_concurrency=9,
                auto_edit_merge_gap=2.0,
                auto_edit_pad_head=1.5,
                auto_edit_pad_tail=1.2,
                bitrate="2m",
                cut_merge_gap=0.9,
                topic_output="ignored-output",
                topic_strict=True,
                topic_max_topics=11,
                topic_title_max_chars=10,
            )
        )
        source_values = {
            name: value for name, value in pipeline_values.items() if name in _SETTINGS_PIPELINE_FIELD_NAMES
        }
        source = SimpleNamespace(**source_values)
        source.lang = "fallback-lang"

        options = build_pipeline_options_from_settings(source)

        passthrough_fields = _PIPELINE_OPTION_FIELD_NAMES - {
            "encoding",
            "force",
            "lang",
            "prompt",
            "asr_backend",
            "topic_llm_model",
            "auto_edit_merge_gap",
            "auto_edit_pad_head",
            "auto_edit_pad_tail",
            "bitrate",
            "topic_output",
            "topic_strict",
            "topic_max_topics",
        }
        for name in passthrough_fields:
            self.assertEqual(getattr(options, name), getattr(source, name), name)

        self.assertEqual(options.encoding, "utf-8")
        self.assertTrue(options.force)
        self.assertEqual(options.lang, "zh")
        self.assertEqual(options.prompt, "")
        self.assertEqual(options.asr_backend, "dashscope_filetrans")
        self.assertEqual(options.topic_llm_model, source.llm_model)
        self.assertEqual(options.auto_edit_merge_gap, 0.5)
        self.assertEqual(options.auto_edit_pad_head, 0.0)
        self.assertEqual(options.auto_edit_pad_tail, 0.0)
        self.assertEqual(options.bitrate, PipelineOptions.bitrate)
        self.assertIsNone(options.topic_output)
        self.assertFalse(options.topic_strict)
        self.assertEqual(options.topic_max_topics, 6)

    def test_get_settings_keeps_pipeline_option_fields_in_sync(self) -> None:
        overrides = {
            "WEB_LANG": "English",
            "ASR_BACKEND": "dashscope_filetrans",
            "DASHSCOPE_ASR_BASE_URL": "https://dashscope.example.invalid",
            "DASHSCOPE_ASR_MODEL": "asr-model",
            "DASHSCOPE_ASR_TASK": "task",
            "DASHSCOPE_ASR_API_KEY": "asr-key",
            "DASHSCOPE_ASR_POLL_SECONDS": "0.1",
            "DASHSCOPE_ASR_TIMEOUT_SECONDS": "1",
            "DASHSCOPE_ASR_LANGUAGE": "en",
            "DASHSCOPE_ASR_LANGUAGE_HINTS": "en,zh",
            "DASHSCOPE_ASR_TEXT": "context",
            "DASHSCOPE_ASR_ENABLE_ITN": "1",
            "DASHSCOPE_ASR_ENABLE_WORDS": "0",
            "DASHSCOPE_ASR_CHANNEL_IDS": "4,5",
            "ASR_SENTENCE_RULE_WITH_PUNC": "0",
            "ASR_WORD_SPLIT_ENABLED": "0",
            "ASR_WORD_SPLIT_ON_COMMA": "0",
            "ASR_WORD_SPLIT_COMMA_PAUSE_S": "-1",
            "ASR_WORD_SPLIT_MIN_CHARS": "0",
            "ASR_WORD_VAD_GAP_S": "-2",
            "ASR_WORD_MAX_SEGMENT_S": "0.5",
            "ASR_NO_SPEECH_GAP_S": "0.1",
            "ASR_INSERT_NO_SPEECH": "0",
            "ASR_INSERT_HEAD_NO_SPEECH": "0",
            "ASR_OSS_ENDPOINT": "https://oss.example.invalid",
            "ASR_OSS_BUCKET": "bucket",
            "ASR_OSS_ACCESS_KEY_ID": "ak",
            "ASR_OSS_ACCESS_KEY_SECRET": "sk",
            "ASR_OSS_PREFIX": "prefix",
            "ASR_OSS_SIGNED_URL_TTL_SECONDS": "1",
            "LLM_BASE_URL": "https://llm.example.invalid",
            "LLM_MODEL": "main-model",
            "TOPIC_LLM_MODEL": "topic-model",
            "LLM_API_KEY": "llm-key",
            "LLM_TIMEOUT": "321",
            "LLM_TEMPERATURE": "0.7",
            "LLM_MAX_TOKENS": "999",
            "AUTO_EDIT_LLM_CONCURRENCY": "0",
            "TOPIC_MAX_TOPICS": "12",
            "TOPIC_TITLE_MAX_CHARS": "9",
            "CUT_MERGE_GAP": "1.1",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            options = build_pipeline_options_from_env(
                lang=(os.getenv("WEB_LANG") or "Chinese").strip() or "Chinese",
                llm_model=(os.getenv("LLM_MODEL") or "qwen-plus").strip() or "qwen-plus",
                topic_llm_model=(os.getenv("TOPIC_LLM_MODEL") or os.getenv("LLM_MODEL") or "kimi-k2.5").strip()
                or "kimi-k2.5",
                topic_max_topics=min(6, int((os.getenv("TOPIC_MAX_TOPICS") or "5").strip() or "5")),
            )

        expected = {name: getattr(options, name) for name in _SETTINGS_PIPELINE_FIELD_NAMES}
        expected.update(
            {
                "asr_dashscope_poll_seconds": max(0.5, options.asr_dashscope_poll_seconds),
                "asr_dashscope_timeout_seconds": max(30.0, options.asr_dashscope_timeout_seconds),
                "asr_dashscope_word_split_comma_pause_s": max(0.0, options.asr_dashscope_word_split_comma_pause_s),
                "asr_dashscope_word_split_min_chars": max(1, options.asr_dashscope_word_split_min_chars),
                "asr_dashscope_word_vad_gap_s": max(0.0, options.asr_dashscope_word_vad_gap_s),
                "asr_dashscope_word_max_segment_s": max(1.0, options.asr_dashscope_word_max_segment_s),
                "asr_dashscope_no_speech_gap_s": max(0.2, options.asr_dashscope_no_speech_gap_s),
                "asr_oss_signed_url_ttl_seconds": max(60, options.asr_oss_signed_url_ttl_seconds),
                "auto_edit_llm_concurrency": max(1, options.auto_edit_llm_concurrency),
                "topic_max_topics": min(6, options.topic_max_topics),
            }
        )

        for name, expected_value in expected.items():
            self.assertEqual(getattr(settings, name), expected_value, name)


if __name__ == "__main__":
    unittest.main()
