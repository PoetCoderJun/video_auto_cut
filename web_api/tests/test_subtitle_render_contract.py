from __future__ import annotations

import unittest

from video_auto_cut.rendering.subtitle_render_contract import (
    build_sparse_highlight_text,
    build_subtitle_render_v1_contract,
    request_subtitle_style_contract,
)


class SubtitleRenderContractTest(unittest.TestCase):
    def test_build_sparse_highlight_text_uses_index_and_text_only(self) -> None:
        payload = build_sparse_highlight_text(
            [
                {"index": 1, "start": 0.0, "end": 1.2, "text": "先给结论"},
                {"index": 2, "start": 1.2, "end": 2.4, "text": "再补充动作"},
            ]
        )

        self.assertEqual(payload, "1\t先给结论\n2\t再补充动作")

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

    def test_request_subtitle_style_contract_parses_sparse_terms_and_keeps_original_terms(self) -> None:
        captions = [
            {"index": 1, "start": 0.0, "end": 1.2, "text": "真正重点先说"},
            {"index": 2, "start": 1.2, "end": 2.4, "text": "然后补动作结果"},
            {"index": 3, "start": 2.4, "end": 3.6, "text": "普通收尾"},
        ]

        def fake_request_text(_cfg, messages):
            self.assertIn("1\t真正重点先说", messages[-1]["content"])
            self.assertIn("2\t然后补动作结果", messages[-1]["content"])
            return "1\t重点 不存在\n2\t动作结果\n"

        payload = request_subtitle_style_contract(
            captions=captions,
            subtitle_theme="black",
            llm_config={"base_url": "https://example.com/v1", "model": "qwen-plus"},
            request_text_fn=fake_request_text,
        )

        self.assertEqual(payload["subtitleTheme"], "black")
        self.assertEqual(payload["captions"][0]["highlights"], ["重点"])
        self.assertEqual(payload["captions"][1]["highlights"], ["动作结果"])
        self.assertEqual(payload["captions"][2]["highlights"], [])

    def test_request_subtitle_style_contract_uses_single_sparse_request_without_chunking(self) -> None:
        captions = [
            {"index": index + 1, "start": index * 1.0, "end": index * 1.0 + 0.8, "text": f"第{index + 1}句重点信息"}
            for index in range(14)
        ]
        seen_calls: list[str] = []

        def fake_request_text(_cfg, messages):
            seen_calls.append(messages[-1]["content"])
            return "14\t重点信息\n"

        payload = request_subtitle_style_contract(
            captions=captions,
            llm_config={"base_url": "https://example.com/v1", "model": "qwen-plus"},
            request_text_fn=fake_request_text,
        )

        self.assertEqual(len(seen_calls), 1)
        self.assertIn("1\t第1句重点信息", seen_calls[0])
        self.assertIn("14\t第14句重点信息", seen_calls[0])
        self.assertEqual(len(payload["captions"]), 14)
        self.assertEqual(payload["captions"][13]["highlights"], ["重点信息"])

    def test_request_subtitle_style_contract_discards_sentence_level_highlights(self) -> None:
        captions = [
            {"index": 1, "start": 0.0, "end": 1.2, "text": "那么二五年香港续签签证有四大变化"},
        ]

        def fake_request_text(_cfg, _messages):
            return "1\t那么二五年香港续签签证有四大变化\n"

        payload = request_subtitle_style_contract(
            captions=captions,
            llm_config={"base_url": "https://example.com/v1", "model": "qwen-plus"},
            request_text_fn=fake_request_text,
        )

        self.assertEqual(payload["captions"][0]["highlights"], [])

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
