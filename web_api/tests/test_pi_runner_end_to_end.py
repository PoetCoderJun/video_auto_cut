from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.chapter.scripts.run_chapter import main as run_chapter
from skills.delete.scripts.run_delete import main as run_delete
from skills.polish.scripts.run_polish import main as run_polish
from web_api.utils.srt_utils import build_step1_lines_from_json, write_final_step1_srt


SRT_SAMPLE = """1
00:00:00,000 --> 00:00:01,000
前面这句说错了

2
00:00:01,200 --> 00:00:02,200
后面这句是正确表达

3
00:00:02,400 --> 00:00:03,400
再补一句自然一点
"""


class PiRunnerEndToEndTests(unittest.TestCase):
    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_raw_srt_to_final_srt_and_chapters_via_three_skill_scripts(self, mock_chat) -> None:
        mock_chat.side_effect = [
            json.dumps(
                {
                    "lines": [
                        {"line_id": 1, "action": "REMOVE", "reason": "被后文覆盖"},
                        {"line_id": 2, "action": "KEEP", "reason": "保留"},
                        {"line_id": 3, "action": "KEEP", "reason": "保留"},
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "lines": [
                        {"line_id": 2, "text": "后面这句是正确表达", "reason": "润色"},
                        {"line_id": 3, "text": "再补一句自然一点", "reason": "润色"},
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "chapters": [
                        {"chapter_id": 1, "title": "开场", "block_range": "1-2"},
                    ]
                },
                ensure_ascii=False,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_srt = root / "input.srt"
            delete_json = root / "delete.json"
            polish_json = root / "polish.json"
            chapters_json = root / "chapters.json"
            final_srt = root / "final_step1.srt"
            input_srt.write_text(SRT_SAMPLE, encoding="utf-8")

            common = [
                "--llm-base-url", "http://localhost:8000",
                "--llm-model", "test-model",
            ]
            self.assertEqual(run_delete(["--input", str(input_srt), "--output", str(delete_json), *common]), 0)
            self.assertEqual(run_polish(["--input", str(delete_json), "--output", str(polish_json), *common]), 0)
            self.assertEqual(run_chapter(["--input", str(polish_json), "--output", str(chapters_json), *common]), 0)

            lines = build_step1_lines_from_json(polish_json)
            write_final_step1_srt(lines, final_srt, "utf-8")
            final_srt_text = final_srt.read_text(encoding="utf-8")
            chapters = json.loads(chapters_json.read_text(encoding="utf-8"))["topics"]

        self.assertIn("<<REMOVE>> 前面这句说错了", final_srt_text)
        self.assertIn("后面这句是正确表达", final_srt_text)
        self.assertIn("再补一句自然一点", final_srt_text)
        self.assertEqual(chapters, [
            {
                "chapter_id": 1,
                "title": "开场",
                "start": 1.2,
                "end": 3.4,
                "block_range": "1-2",
            }
        ])


if __name__ == "__main__":
    unittest.main()
