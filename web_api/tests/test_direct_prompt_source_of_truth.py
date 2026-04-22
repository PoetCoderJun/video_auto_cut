from __future__ import annotations

import unittest
from pathlib import Path

from video_auto_cut.editing.direct_prompts import (
    DIRECT_PROMPTS_DIR,
    _load_prompt_template,
    build_chapter_messages,
    build_delete_messages,
    build_highlight_messages,
    build_polish_messages,
)


class DirectPromptSourceOfTruthTests(unittest.TestCase):
    def test_delete_system_prompt_is_loaded_from_skills_direct_prompts(self) -> None:
        expected = _load_prompt_template("delete")
        self.assertEqual(build_delete_messages("1\t第一句")[0]["content"], expected)

    def test_polish_system_prompt_is_loaded_from_skills_direct_prompts(self) -> None:
        expected = _load_prompt_template("polish")
        self.assertEqual(build_polish_messages("1\t原句")[0]["content"], expected)

    def test_chapter_system_prompt_appends_runtime_rules_after_file_content(self) -> None:
        template = _load_prompt_template("chapter")
        prompt = build_chapter_messages(
            "【1】第一段",
            title_max_chars=5,
            max_chapters=2,
            chapter_policy_hint="横屏视频章节约束",
        )[0]["content"]
        self.assertTrue(prompt.startswith(template))
        self.assertIn("- 当前按横屏视频章节约束处理，本次最多只能分成 2 章。", prompt)
        self.assertIn("- 标题绝不能超过 5 个字。", prompt)

    def test_highlight_system_prompt_appends_theme_note_after_file_content(self) -> None:
        template = _load_prompt_template("highlight")
        prompt = build_highlight_messages("1\t香港", subtitle_theme="white")[0]["content"]
        self.assertTrue(prompt.startswith(template))
        self.assertIn("额外说明：渲染主题固定为 `white`，你无需输出主题信息。", prompt)


if __name__ == "__main__":
    unittest.main()
