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
    def test_delete_prompt_text_is_loaded_into_user_message_from_skills_direct_prompts(self) -> None:
        expected = _load_prompt_template("delete")
        message = build_delete_messages("1\t第一句")[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(expected))
        self.assertIn("请直接处理下面的 delete 输入", message["content"])
        self.assertIn("1\t第一句", message["content"])

    def test_polish_prompt_text_is_loaded_into_user_message_from_skills_direct_prompts(self) -> None:
        expected = _load_prompt_template("polish")
        message = build_polish_messages("1\t原句")[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(expected))
        self.assertIn("请直接处理下面的 polish 输入", message["content"])
        self.assertIn("1\t原句", message["content"])

    def test_chapter_prompt_appends_runtime_rules_inside_user_message(self) -> None:
        template = _load_prompt_template("chapter")
        message = build_chapter_messages(
            "【1】第一段",
            title_max_chars=5,
            max_chapters=2,
            chapter_policy_hint="横屏视频章节约束",
        )[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(template))
        self.assertIn("- 当前按横屏视频章节约束处理，本次最多只能分成 2 章。", message["content"])
        self.assertIn("- 标题绝不能超过 5 个字。", message["content"])
        self.assertIn("【1】第一段", message["content"])

    def test_highlight_prompt_appends_theme_note_inside_user_message(self) -> None:
        template = _load_prompt_template("highlight")
        message = build_highlight_messages("1\t香港", subtitle_theme="white")[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(template))
        self.assertIn("额外说明：渲染主题固定为 `white`，你无需输出主题信息。", message["content"])
        self.assertIn("1\t香港", message["content"])


if __name__ == "__main__":
    unittest.main()
