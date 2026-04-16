from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from video_auto_cut.asr.dashscope_filetrans import DashScopeFiletransClient, DashScopeFiletransConfig


def _client() -> DashScopeFiletransClient:
    return DashScopeFiletransClient(
        DashScopeFiletransConfig(
            base_url="https://example.com",
            api_key="test-key",
            model="test-model",
            task=None,
            poll_seconds=1.0,
            timeout_seconds=30.0,
            language="zh",
            language_hints=(),
            text="香港续签",
            enable_itn=True,
            enable_words=True,
            channel_ids=(0,),
            word_split_enabled=True,
            word_split_on_comma=True,
            word_split_comma_pause_s=0.4,
            word_split_min_chars=12,
            word_vad_gap_s=1.0,
            word_max_segment_s=8.0,
        )
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class DashScopeFiletransHttpTests(unittest.TestCase):
    @patch("video_auto_cut.asr.dashscope_filetrans.time.sleep")
    @patch("video_auto_cut.asr.dashscope_filetrans.urllib.request.urlopen")
    def test_post_json_retries_on_retryable_http_error_then_succeeds(self, mock_urlopen, mock_sleep) -> None:
        retry_exc = urllib.error.HTTPError(
            url="https://example.com/api/v1/services/audio/asr/transcription",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b"busy"),
        )
        mock_urlopen.side_effect = [
            retry_exc,
            _FakeResponse({"output": {"task_id": "task-1"}}),
        ]

        payload = _client()._post_json("/api/v1/services/audio/asr/transcription", {"x": 1})

        self.assertEqual(payload, {"output": {"task_id": "task-1"}})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("video_auto_cut.asr.dashscope_filetrans.time.sleep")
    @patch("video_auto_cut.asr.dashscope_filetrans.urllib.request.urlopen")
    def test_get_json_does_not_retry_non_retryable_http_error(self, mock_urlopen, mock_sleep) -> None:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api/v1/tasks/task-1",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b"bad input"),
        )

        with self.assertRaisesRegex(RuntimeError, "DashScope poll failed: HTTP 400: bad input"):
            _client()._get_json("/api/v1/tasks/task-1")

        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("video_auto_cut.asr.dashscope_filetrans.DashScopeFiletransClient._post_json")
    def test_submit_fallback_to_file_urls_preserves_original_text_and_language(self, mock_post_json) -> None:
        mock_post_json.side_effect = [
            RuntimeError("DashScope submit failed: HTTP 400: InvalidParameter url"),
            {"output": {"task_id": "task-2"}},
        ]

        response = _client().submit(
            file_url="https://example.com/audio.wav",
            lang="zh-cn",
            prompt="原始上下文提示",
        )

        self.assertEqual(response.task_id, "task-2")
        self.assertEqual(mock_post_json.call_count, 2)
        first_payload = mock_post_json.call_args_list[0].args[1]
        second_payload = mock_post_json.call_args_list[1].args[1]
        self.assertEqual(first_payload["parameters"]["text"], "原始上下文提示")
        self.assertEqual(second_payload["parameters"]["text"], "原始上下文提示")
        self.assertEqual(first_payload["parameters"]["language"], "zh")
        self.assertEqual(second_payload["parameters"]["language"], "zh")
        self.assertEqual(second_payload["input"], {"file_urls": ["https://example.com/audio.wav"]})


if __name__ == "__main__":
    unittest.main()
