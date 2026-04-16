from __future__ import annotations

import os
import unittest
from argparse import Namespace
from unittest.mock import patch

from video_auto_cut.orchestration.full_pipeline import _build_cli_pipeline_options


class FullPipelineCliOptionsTest(unittest.TestCase):
    def test_build_cli_pipeline_options_shares_single_override_path(self) -> None:
        args = Namespace(
            encoding="utf-8",
            force=True,
            lang="Chinese",
            prompt="prompt",
            asr_backend=None,
            asr_dashscope_base_url="  https://cli.example.invalid  ",
            asr_dashscope_model=" cli-asr ",
            asr_dashscope_api_key=None,
            llm_base_url=None,
            llm_model=" cli-model ",
            llm_api_key=None,
            llm_timeout=123,
            llm_temperature=0.7,
            llm_max_tokens=456,
            auto_edit_merge_gap=0.8,
            auto_edit_pad_head=0.3,
            auto_edit_pad_tail=0.4,
            bitrate="12m",
            cut_merge_gap=0.9,
            topic_output="topics.json",
            topic_strict=True,
            topic_max_topics=7,
            topic_title_max_chars=8,
        )
        env = {
            "ASR_BACKEND": "dashscope_filetrans",
            "DASHSCOPE_ASR_API_KEY": "env-asr-key",
            "LLM_BASE_URL": "https://env-llm.example.invalid",
            "LLM_API_KEY": "env-llm-key",
        }

        with patch.dict(os.environ, env, clear=False):
            options = _build_cli_pipeline_options(args)

        self.assertEqual(options.asr_backend, "dashscope_filetrans")
        self.assertEqual(options.asr_dashscope_base_url, "https://cli.example.invalid")
        self.assertEqual(options.asr_dashscope_model, "cli-asr")
        self.assertEqual(options.asr_dashscope_api_key, "env-asr-key")
        self.assertEqual(options.llm_base_url, "https://env-llm.example.invalid")
        self.assertEqual(options.llm_model, "cli-model")
        self.assertEqual(options.llm_api_key, "env-llm-key")
        self.assertEqual(options.llm_timeout, 123)
        self.assertEqual(options.llm_temperature, 0.7)
        self.assertEqual(options.llm_max_tokens, 456)
        self.assertEqual(options.auto_edit_merge_gap, 0.8)
        self.assertEqual(options.auto_edit_pad_head, 0.3)
        self.assertEqual(options.auto_edit_pad_tail, 0.4)
        self.assertEqual(options.bitrate, "12m")
        self.assertEqual(options.cut_merge_gap, 0.9)
        self.assertEqual(options.topic_output, "topics.json")
        self.assertTrue(options.topic_strict)
        self.assertEqual(options.topic_max_topics, 7)
        self.assertEqual(options.topic_title_max_chars, 8)


if __name__ == "__main__":
    unittest.main()
