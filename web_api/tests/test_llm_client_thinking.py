from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from video_auto_cut.editing import llm_client
from video_auto_cut.editing.auto_edit import AutoEdit
from video_auto_cut.editing.topic_segment import TopicSegmenter


class DummyAutoEditArgs:
    def __init__(self) -> None:
        self.inputs = []
        self.encoding = "utf-8"
        self.force = False
        self.auto_edit_llm = True
        self.auto_edit_merge_gap = 0.5
        self.auto_edit_pad_head = 0.0
        self.auto_edit_pad_tail = 0.0
        self.auto_edit_topics = False
        self.topic_strict = False
        self.topic_output = None
        self.llm_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.llm_model = "kimi-k2.5"
        self.llm_api_key = "secret"
        self.llm_timeout = 60
        self.llm_temperature = 0.0
        self.llm_max_tokens = None


class DummyTopicArgs:
    def __init__(self) -> None:
        self.inputs = []
        self.encoding = "utf-8"
        self.topic_max_topics = 8
        self.topic_title_max_chars = 6
        self.topic_strict = False
        self.llm_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.llm_model = "kimi-k2.5"
        self.llm_api_key = "secret"
        self.llm_timeout = 60
        self.llm_temperature = 0.2
        self.llm_max_tokens = None


class LlmClientThinkingTest(unittest.TestCase):
    def setUp(self) -> None:
        llm_client._OPENAI_CLIENTS_BY_CFG.clear()

    def test_build_llm_config_reads_enable_thinking_env(self) -> None:
        with patch.dict(os.environ, {"LLM_ENABLE_THINKING": "1"}, clear=False):
            cfg = llm_client.build_llm_config(
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="kimi-k2.5",
            )

        self.assertTrue(cfg["enable_thinking"])

    def test_chat_completion_uses_openai_sdk_and_thinking_flag(self) -> None:
        cfg = {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "kimi-k2.5",
            "api_key": "secret",
            "timeout": 60,
            "temperature": 0.0,
            "max_tokens": None,
            "request_retries": 1,
            "enable_thinking": True,
        }
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        client = MagicMock()
        client.chat.completions.create.return_value = response

        with patch("video_auto_cut.editing.llm_client.OpenAI", return_value=client) as mock_openai:
            result = llm_client.chat_completion(cfg, [{"role": "user", "content": "hello"}])

        self.assertEqual(result, "ok")
        mock_openai.assert_called_once_with(
            api_key="secret",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        client.chat.completions.create.assert_called_once()
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "kimi-k2.5")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(kwargs["extra_body"], {"enable_thinking": True})

    def test_chat_completion_reuses_client_for_same_connection(self) -> None:
        cfg_a = {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "kimi-k2.5",
            "api_key": "secret",
            "timeout": 60,
            "temperature": 0.0,
            "max_tokens": None,
            "request_retries": 1,
            "enable_thinking": False,
        }
        cfg_b = {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "api_key": "secret",
            "timeout": 180,
            "temperature": 0.8,
            "max_tokens": 1024,
            "request_retries": 5,
            "enable_thinking": True,
        }
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        client = MagicMock()
        client.chat.completions.create.return_value = response

        with patch("video_auto_cut.editing.llm_client.OpenAI", return_value=client) as mock_openai:
            result_a = llm_client.chat_completion(cfg_a, [{"role": "user", "content": "hello"}])
            result_b = llm_client.chat_completion(cfg_b, [{"role": "user", "content": "world"}])

        self.assertEqual(result_a, "ok")
        self.assertEqual(result_b, "ok")
        mock_openai.assert_called_once_with(
            api_key="secret",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_chat_completion_creates_new_client_for_different_connection(self) -> None:
        cfg_a = {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "kimi-k2.5",
            "api_key": "secret-a",
            "timeout": 60,
            "temperature": 0.0,
            "max_tokens": None,
            "request_retries": 1,
            "enable_thinking": False,
        }
        cfg_b = {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1-mini",
            "api_key": "secret-b",
            "timeout": 60,
            "temperature": 0.0,
            "max_tokens": None,
            "request_retries": 1,
            "enable_thinking": False,
        }
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        client = MagicMock()
        client.chat.completions.create.return_value = response

        with patch("video_auto_cut.editing.llm_client.OpenAI", return_value=client) as mock_openai:
            llm_client.chat_completion(cfg_a, [{"role": "user", "content": "hello"}])
            llm_client.chat_completion(cfg_b, [{"role": "user", "content": "world"}])

        self.assertEqual(mock_openai.call_count, 2)

    def test_auto_edit_disables_thinking_by_default(self) -> None:
        with patch(
            "video_auto_cut.editing.auto_edit.llm_utils.build_llm_config",
            return_value={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "kimi-k2.5",
                "api_key": "secret",
                "enable_thinking": False,
            },
        ) as mock_build:
            AutoEdit(DummyAutoEditArgs())

        mock_build.assert_called_once_with(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="kimi-k2.5",
            api_key="secret",
            timeout=60,
            temperature=0.0,
            max_tokens=None,
            enable_thinking=False,
        )

    def test_topic_segmenter_disables_thinking_by_default(self) -> None:
        with patch(
            "video_auto_cut.editing.topic_segment.llm_utils.build_llm_config",
            return_value={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "kimi-k2.5",
                "api_key": "secret",
                "enable_thinking": False,
            },
        ) as mock_build:
            TopicSegmenter(DummyTopicArgs())

        mock_build.assert_called_once_with(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="kimi-k2.5",
            api_key="secret",
            timeout=60,
            temperature=0.2,
            max_tokens=None,
            enable_thinking=False,
        )


if __name__ == "__main__":
    unittest.main()
