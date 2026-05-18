from __future__ import annotations

import json
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import srt

from video_auto_cut.direct_prompt_runner import (
    TestPromptRequest,
    build_subtitles_from_lines,
    run_test_prompt,
)
from video_auto_cut.editing.direct_prompts import (
    DIRECT_PROMPTS_DIR,
    build_delete_messages,
    build_polish_messages,
)
from video_auto_cut.rendering.subtitle_render_contract import build_subtitle_render_v1_contract
from video_auto_cut.shared.test_text_io import build_test_lines_from_srt, write_test_text


class CoreContractTest(unittest.TestCase):
    def test_direct_prompt_source_files_are_the_runtime_source(self) -> None:
        expected = {
            "delete.md",
            "polish.md",
            "delete-with-reference.md",
            "polish-with-reference.md",
            "chapter.md",
            "highlight.md",
        }
        self.assertEqual({path.name for path in DIRECT_PROMPTS_DIR.glob("*.md")}, expected)

        message = build_delete_messages("1\t你好")[0]["content"]
        self.assertIn((DIRECT_PROMPTS_DIR / "delete.md").read_text(encoding="utf-8").strip()[:40], message)
        self.assertNotIn("参考口播脚本", message)

        reference_message = build_polish_messages("1\t你好", script="参考稿")[0]["content"]
        self.assertIn("参考口播脚本", reference_message)
        self.assertIn("参考稿", reference_message)

    def test_delete_parser_preserves_timing_and_marks_removed_lines(self) -> None:
        request = TestPromptRequest(
            task="delete",
            llm_config={"base_url": "http://llm.invalid", "model": "test", "api_key": "test"},
            segments=[
                {"id": 1, "start": 0.0, "end": 1.0, "text": "嗯"},
                {"id": 2, "start": 1.0, "end": 2.0, "text": "第一句有效内容"},
            ],
        )
        with patch(
            "video_auto_cut.direct_prompt_runner._run_direct_prompt",
            return_value=("", False, None),
        ):
            artifacts = run_test_prompt(request)

        self.assertEqual([line["line_id"] for line in artifacts.lines], [1, 2])
        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertFalse(artifacts.lines[1]["user_final_remove"])
        self.assertEqual(artifacts.lines[1]["optimized_text"], "第一句有效内容")

    def test_srt_test_text_and_subtitle_round_trip(self) -> None:
        subtitles = [
            srt.Subtitle(index=1, start=datetime.timedelta(seconds=0), end=datetime.timedelta(seconds=1), content="保留这一句"),
            srt.Subtitle(index=2, start=datetime.timedelta(seconds=1), end=datetime.timedelta(seconds=2), content="<remove>删除这一句"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            srt_path = Path(tmp) / "input.srt"
            text_path = Path(tmp) / "input.test.txt"
            srt_path.write_text(srt.compose(subtitles, reindex=False), encoding="utf-8")
            lines = build_test_lines_from_srt(srt_path, "utf-8")
            write_test_text(lines, text_path)

        rebuilt = build_subtitles_from_lines(lines)
        self.assertEqual(len(rebuilt), 2)
        self.assertEqual(rebuilt[0].content, "保留这一句")
        self.assertTrue(rebuilt[1].content.startswith("<remove>"))

    def test_subtitle_render_contract_is_json_serializable(self) -> None:
        payload = build_subtitle_render_v1_contract(
            captions=[{"index": 1, "start": 0.0, "end": 1.2, "text": "重点内容"}],
            segments=[{"start": 0.0, "end": 1.2}],
            topics=[{"title": "开场", "start": 0.0, "end": 1.2}],
            style_contract={"captions": [{"highlights": [{"text": "重点"}]}]},
            output_name="sample.mp4",
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("subtitle-render.v1", encoded)
        self.assertIn("重点", encoded)


if __name__ == "__main__":
    unittest.main()
