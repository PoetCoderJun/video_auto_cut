from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from web_api.services.render_caption_labels import attach_llm_labels_to_captions


class RenderCaptionLabelsTest(unittest.TestCase):
    def test_attach_llm_labels_to_captions_skips_when_llm_config_missing(self) -> None:
        captions = [
            {
                "index": 1,
                "start": 0.0,
                "end": 2.0,
                "text": "讲重点",
                "tokens": [{"text": "讲", "start": 0.0, "end": 1.0}],
            }
        ]
        settings = SimpleNamespace(
            llm_base_url=None,
            llm_model=None,
            llm_api_key=None,
            llm_timeout=60,
            llm_max_tokens=None,
        )

        with patch("web_api.services.render_caption_labels.get_settings", return_value=settings), patch(
            "web_api.services.render_caption_labels.llm_utils.build_llm_config",
            return_value={"base_url": "", "model": ""},
        ) as mock_build_llm_config, patch(
            "web_api.services.render_caption_labels.llm_utils.request_json"
        ) as mock_request_json:
            result = attach_llm_labels_to_captions(captions=captions, job_id="job-no-llm")

        self.assertEqual(result, captions)
        mock_build_llm_config.assert_called_once()
        mock_request_json.assert_not_called()

    def test_attach_llm_labels_to_captions_normalizes_valid_payload(self) -> None:
        captions = [
            {
                "index": 1,
                "start": 0.0,
                "end": 3.0,
                "text": "先讲重点结论",
                "tokens": [
                    {"text": "先", "start": 0.0, "end": 0.5},
                    {"text": "讲", "start": 0.5, "end": 1.0},
                    {"text": "重点", "start": 1.0, "end": 2.0},
                    {"text": "结论", "start": 2.0, "end": 3.0},
                ],
            },
            {
                "index": 2,
                "start": 3.0,
                "end": 5.0,
                "text": "继续展开",
                "tokens": [
                    {"text": "继续", "start": 3.0, "end": 4.0},
                    {"text": "展开", "start": 4.0, "end": 5.0},
                ],
            },
        ]
        settings = SimpleNamespace(
            llm_base_url="https://example.com/v1",
            llm_model="qwen-plus",
            llm_api_key="secret",
            llm_timeout=60,
            llm_max_tokens=None,
        )

        def fake_request_json(_cfg, _messages, *, validate, **_kwargs):
            return validate(
                {
                    "labels": [
                        {
                            "index": 1,
                            "badgeText": "核心结论摘要过长会被截断",
                            "emphasisSpans": [
                                {"startToken": 2, "endToken": 4},
                                {"startToken": 2, "endToken": 4},
                                {"startToken": 4, "endToken": 5},
                            ],
                        },
                        {
                            "index": 2,
                            "emphasisSpans": [{"startToken": 1, "endToken": 1}],
                        },
                        {
                            "index": 99,
                            "badgeText": "忽略",
                        },
                    ]
                }
            )

        with patch("web_api.services.render_caption_labels.get_settings", return_value=settings), patch(
            "web_api.services.render_caption_labels.llm_utils.build_llm_config",
            return_value={"base_url": "https://example.com/v1", "model": "qwen-plus"},
        ), patch(
            "web_api.services.render_caption_labels.llm_utils.request_json",
            side_effect=fake_request_json,
        ):
            result = attach_llm_labels_to_captions(captions=captions, job_id="job-label-ok")

        self.assertEqual(
            result[0]["label"],
            {
                "badgeText": "核心结论摘要过长会被截断",
                "emphasisSpans": [{"startToken": 2, "endToken": 4}],
            },
        )
        self.assertNotIn("label", result[1])

    def test_attach_llm_labels_to_captions_omits_labels_when_request_fails(self) -> None:
        captions = [
            {
                "index": 1,
                "start": 0.0,
                "end": 2.0,
                "text": "讲重点",
                "tokens": [{"text": "讲", "start": 0.0, "end": 1.0}],
            }
        ]
        settings = SimpleNamespace(
            llm_base_url="https://example.com/v1",
            llm_model="qwen-plus",
            llm_api_key="secret",
            llm_timeout=60,
            llm_max_tokens=None,
        )

        with patch("web_api.services.render_caption_labels.get_settings", return_value=settings), patch(
            "web_api.services.render_caption_labels.llm_utils.build_llm_config",
            return_value={"base_url": "https://example.com/v1", "model": "qwen-plus"},
        ), patch(
            "web_api.services.render_caption_labels.llm_utils.request_json",
            side_effect=RuntimeError("upstream boom"),
        ):
            result = attach_llm_labels_to_captions(captions=captions, job_id="job-label-fail")

        self.assertEqual(result, captions)


if __name__ == "__main__":
    unittest.main()
