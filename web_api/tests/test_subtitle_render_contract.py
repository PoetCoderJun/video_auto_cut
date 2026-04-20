from __future__ import annotations

import unittest

from video_auto_cut.rendering.subtitle_render_contract import (
    build_subtitle_render_v1_contract,
    request_subtitle_style_contract,
)


class SubtitleRenderContractTest(unittest.TestCase):
    def test_request_subtitle_style_contract_returns_empty_highlights_without_llm(self) -> None:
        payload = request_subtitle_style_contract(
            captions=[
                {"index": 1, "start": 0.0, "end": 1.2, "text": "先给结论"},
                {"index": 2, "start": 1.2, "end": 2.4, "text": "再补充动作"},
            ],
            llm_config={"base_url": "", "model": ""},
        )

        self.assertEqual(payload["version"], "subtitle-style.v1")
        self.assertEqual(payload["subtitleTheme"], "white")
        self.assertEqual(payload["captions"][0]["highlights"], [])
        self.assertEqual(payload["captions"][1]["text"], "再补充动作")

    def test_request_subtitle_style_contract_validates_exact_rows_and_keeps_original_terms(self) -> None:
        captions = [
            {"index": 1, "start": 0.0, "end": 1.2, "text": "真正重点先说"},
            {"index": 2, "start": 1.2, "end": 2.4, "text": "然后补动作结果"},
        ]

        def fake_request_json(_cfg, _messages, *, validate, **_kwargs):
            return validate(
                {
                    "version": "subtitle-style.v1",
                    "subtitleTheme": "black",
                    "captions": [
                        {
                            "start": "00:00:00.000",
                            "end": "00:00:01.200",
                            "text": "真正重点先说",
                            "highlights": ["重点", "不存在"],
                        },
                        {
                            "start": "00:00:01.200",
                            "end": "00:00:02.400",
                            "text": "然后补动作结果",
                            "highlights": [{"text": "动作结果"}],
                        },
                    ],
                }
            )

        payload = request_subtitle_style_contract(
            captions=captions,
            subtitle_theme="black",
            llm_config={"base_url": "https://example.com/v1", "model": "qwen-plus"},
            request_json_fn=fake_request_json,
        )

        self.assertEqual(payload["subtitleTheme"], "black")
        self.assertEqual(payload["captions"][0]["highlights"], ["重点"])
        self.assertEqual(payload["captions"][1]["highlights"], ["动作结果"])

    def test_build_subtitle_render_v1_contract_converts_highlight_terms_to_render_labels(self) -> None:
        contract = build_subtitle_render_v1_contract(
            captions=[
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "text": "先把重点结论讲清楚",
                    "tokens": [
                        {"text": "先", "start": 0.0, "end": 0.4},
                        {"text": "把", "start": 0.4, "end": 0.8},
                    ],
                    "alignmentMode": "exact",
                }
            ],
            segments=[{"start": 0.0, "end": 2.0}],
            topics=[{"title": "第一段", "start": 0.0, "end": 2.0}],
            output_name="demo.mp4",
            style_contract={
                "version": "subtitle-style.v1",
                "subtitleTheme": "white",
                "captions": [
                    {
                        "start": "00:00:00.000",
                        "end": "00:00:02.000",
                        "text": "先把重点结论讲清楚",
                        "highlights": ["重点结论"],
                    }
                ],
            },
        )

        self.assertEqual(contract["version"], "subtitle-render.v1")
        self.assertEqual(contract["subtitleTheme"], "white")
        self.assertEqual(contract["captions"][0]["label"]["highlights"], [{"text": "重点结论"}])
        self.assertEqual(contract["captions"][0]["alignmentMode"], "exact")
        self.assertEqual(contract["topics"][0]["title"], "第一段")


if __name__ == "__main__":
    unittest.main()
