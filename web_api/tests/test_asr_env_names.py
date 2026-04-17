from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_env
from web_api.config import get_settings


class AsrEnvNamesTest(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_prefers_new_dashscope_and_local_env_names(self) -> None:
        overrides = {
            "DASHSCOPE_ASR_BASE_URL": "https://dashscope.aliyuncs.com",
            "DASHSCOPE_ASR_MODEL": "qwen3-asr-flash-filetrans",
            "DASHSCOPE_ASR_API_KEY": "new-key",
            "DASHSCOPE_ASR_POLL_SECONDS": "3.0",
            "DASHSCOPE_ASR_TIMEOUT_SECONDS": "1800",
            "DASHSCOPE_ASR_LANGUAGE": "zh",
            "DASHSCOPE_ASR_ENABLE_ITN": "1",
            "DASHSCOPE_ASR_ENABLE_WORDS": "1",
            "DASHSCOPE_ASR_TEXT": "香港续签",
            "DASHSCOPE_ASR_CHANNEL_IDS": "0,1",
            "ASR_WORD_SPLIT_ENABLED": "0",
            "ASR_INSERT_NO_SPEECH": "0",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.asr_dashscope_api_key, "new-key")
        self.assertEqual(settings.asr_dashscope_language, "zh")
        self.assertTrue(settings.asr_dashscope_enable_itn)
        self.assertEqual(settings.asr_dashscope_context, "香港续签")
        self.assertEqual(settings.asr_dashscope_channel_ids, (0, 1))
        self.assertFalse(settings.asr_dashscope_word_split_enabled)
        self.assertFalse(settings.asr_dashscope_insert_no_speech)

    def test_legacy_aliases_no_longer_override_asr_settings(self) -> None:
        overrides = {
            "DASHSCOPE_ASR_ENABLE_WORDS": "",
            "ASR_WORD_SPLIT_ENABLED": "",
            "ASR_DASHSCOPE_API_KEY": "legacy-key",
            "ASR_DASHSCOPE_BASE_URL": "https://legacy.example.invalid",
            "ASR_DASHSCOPE_MODEL": "legacy-model",
            "ASR_DASHSCOPE_CONTEXT": "legacy-context",
            "ASR_DASHSCOPE_ENABLE_WORDS": "0",
            "ASR_DASHSCOPE_WORD_SPLIT_ENABLED": "0",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertIsNone(settings.asr_dashscope_api_key)
        self.assertEqual(settings.asr_dashscope_base_url, "https://dashscope-intl.aliyuncs.com")
        self.assertEqual(settings.asr_dashscope_model, "qwen3-asr-flash-filetrans")
        self.assertEqual(settings.asr_dashscope_context, "")
        self.assertTrue(settings.asr_dashscope_enable_words)
        self.assertTrue(settings.asr_dashscope_word_split_enabled)

    def test_legacy_asr_oss_env_names_no_longer_override_oss_settings(self) -> None:
        overrides = {
            "OSS_ENDPOINT": "",
            "OSS_BUCKET": "",
            "OSS_ACCESS_KEY_ID": "",
            "OSS_ACCESS_KEY_SECRET": "",
            "OSS_PREFIX": "",
            "OSS_SIGNED_URL_TTL_SECONDS": "",
            "ASR_OSS_ENDPOINT": "https://legacy-oss.example.invalid",
            "ASR_OSS_BUCKET": "legacy-bucket",
            "ASR_OSS_ACCESS_KEY_ID": "legacy-ak",
            "ASR_OSS_ACCESS_KEY_SECRET": "legacy-sk",
            "ASR_OSS_PREFIX": "legacy/prefix",
            "ASR_OSS_SIGNED_URL_TTL_SECONDS": "1200",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertIsNone(settings.asr_oss_endpoint)
        self.assertIsNone(settings.asr_oss_bucket)
        self.assertIsNone(settings.asr_oss_access_key_id)
        self.assertIsNone(settings.asr_oss_access_key_secret)
        self.assertEqual(settings.asr_oss_prefix, "video-auto-cut/asr")
        self.assertEqual(settings.asr_oss_signed_url_ttl_seconds, 86400)

    def test_core_env_builder_matches_new_asr_env_shape(self) -> None:
        overrides = {
            "DASHSCOPE_ASR_BASE_URL": "https://dashscope.aliyuncs.com",
            "DASHSCOPE_ASR_MODEL": "qwen3-asr-flash-filetrans",
            "DASHSCOPE_ASR_API_KEY": "new-key",
            "DASHSCOPE_ASR_LANGUAGE": "zh",
            "DASHSCOPE_ASR_TEXT": "香港续签",
            "DASHSCOPE_ASR_CHANNEL_IDS": "0,1",
            "ASR_WORD_SPLIT_ENABLED": "0",
            "ASR_INSERT_NO_SPEECH": "0",
        }
        with patch.dict(os.environ, overrides, clear=False):
            options = build_pipeline_options_from_env()

        self.assertEqual(options.asr_dashscope_api_key, "new-key")
        self.assertEqual(options.asr_dashscope_language, "zh")
        self.assertEqual(options.asr_dashscope_context, "香港续签")
        self.assertEqual(options.asr_dashscope_channel_ids, (0, 1))
        self.assertFalse(options.asr_dashscope_word_split_enabled)
        self.assertFalse(options.asr_dashscope_insert_no_speech)

    def test_settings_and_pipeline_builder_share_same_env_parsing(self) -> None:
        overrides = {
            "OSS_ENDPOINT": "https://oss-cn-test.aliyuncs.com",
            "OSS_BUCKET": "bucket-a",
            "OSS_ACCESS_KEY_ID": "ak",
            "OSS_ACCESS_KEY_SECRET": "sk",
            "OSS_PREFIX": "jobs/asr",
            "OSS_SIGNED_URL_TTL_SECONDS": "1200",
            "LLM_MODEL": "kimi-k2.5",
            "LLM_MAX_TOKENS": "4096",
            "AUTO_EDIT_LLM_CONCURRENCY": "7",
        }
        with patch.dict(os.environ, overrides, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            options = build_pipeline_options_from_env(
                llm_model="qwen-plus",
                topic_llm_model="kimi-k2.5",
            )

        self.assertEqual(settings.asr_oss_endpoint, options.asr_oss_endpoint)
        self.assertEqual(settings.asr_oss_bucket, options.asr_oss_bucket)
        self.assertEqual(settings.asr_oss_prefix, options.asr_oss_prefix)
        self.assertEqual(settings.asr_oss_signed_url_ttl_seconds, options.asr_oss_signed_url_ttl_seconds)
        self.assertEqual(settings.llm_max_tokens, options.llm_max_tokens)
        self.assertEqual(settings.auto_edit_llm_concurrency, options.auto_edit_llm_concurrency)
