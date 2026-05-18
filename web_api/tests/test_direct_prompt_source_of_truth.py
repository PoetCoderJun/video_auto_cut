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
        self.assertNotIn("## 参考口播脚本", message["content"])
        self.assertNotIn("更接近最终准确表达", message["content"])
        self.assertIn("1\t第一句", message["content"])

    def test_delete_with_reference_prompt_is_separate_source(self) -> None:
        expected = _load_prompt_template("delete-with-reference")
        message = build_delete_messages("1\tASR 错句", script="这是脚本里的准确说法")[0]
        self.assertTrue(message["content"].startswith(expected))
        self.assertIn("优先用参考口播脚本判断", message["content"])
        self.assertIn("## 参考口播脚本", message["content"])
        self.assertIn("这是脚本里的准确说法", message["content"])
        self.assertIn("## 待处理字幕", message["content"])
        self.assertIn("1\tASR 错句", message["content"])

    def test_delete_prompt_preserves_handcrafted_overview_verbatim(self) -> None:
        expected_overview = (
            "## Overview\n\n"
            "你是一个剪辑口播、增加内容密度的剪辑助手\n"
            "在对口播的过程中：\n"
            "1. 录制人往往会讲错（不一定讲完），后面就可能再讲一次或者多次，直到讲对为止，后面讲的时候未必和前面完全一致，但是如果出现了前面讲过的语义后面重复出现，则需要将前面出现的语音的行删除掉\n"
            "2. 录制人有时会出现思考和卡顿，或者语气词停顿很久，单独的语气词的行也要删掉"
        )
        self.assertIn(expected_overview, _load_prompt_template("delete"))

    def test_delete_prompt_states_semantic_coverage_principle(self) -> None:
        prompt = _load_prompt_template("delete")
        self.assertIn("完整覆盖前文的核心语义", prompt)
        self.assertIn("可以替代前文且不丢信息", prompt)
        self.assertIn("后文只是补充、展开、承接", prompt)
        self.assertIn("新的信息增量", prompt)

    def test_delete_prompt_states_fast_conservative_decision_principle(self) -> None:
        prompt = _load_prompt_template("delete")
        self.assertIn("快速、保守的剪辑判断", prompt)
        self.assertIn("不要穷尽所有远距离相似关系", prompt)
        self.assertIn("连续或近邻的重说", prompt)
        self.assertIn("只是主题相似但不是同一表达的重新完成", prompt)
        self.assertIn("只输出确定删除的行号", prompt)

    def test_polish_prompt_text_is_loaded_into_user_message_from_skills_direct_prompts(self) -> None:
        expected = _load_prompt_template("polish")
        message = build_polish_messages("1\t原句")[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(expected))
        self.assertNotIn("## 参考口播脚本", message["content"])
        self.assertNotIn("以参考口播脚本的措辞", message["content"])
        self.assertIn("1\t原句", message["content"])

    def test_polish_with_reference_prompt_is_separate_source(self) -> None:
        expected = _load_prompt_template("polish-with-reference")
        message = build_polish_messages("1\t错别字", script="脚本里的专有名词 OpenAI")[0]
        self.assertTrue(message["content"].startswith(expected))
        self.assertIn("以参考口播脚本的措辞", message["content"])
        self.assertIn("## 参考口播脚本", message["content"])
        self.assertIn("脚本里的专有名词 OpenAI", message["content"])
        self.assertIn("## 待处理字幕", message["content"])
        self.assertIn("1\t错别字", message["content"])

    def test_chapter_prompt_uses_file_text_without_runtime_rules(self) -> None:
        template = _load_prompt_template("chapter")
        message = build_chapter_messages(
            "【1】第一段",
            title_max_chars=5,
            max_chapters=2,
            chapter_policy_hint="横屏视频章节约束",
        )[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(template))
        self.assertNotIn("横屏视频章节约束", message["content"])
        self.assertNotIn("本次最多只能分成 2 章", message["content"])
        self.assertNotIn("标题绝不能超过 4 个字", message["content"])
        self.assertIn("【1】第一段", message["content"])

    def test_highlight_prompt_uses_file_text_without_theme_note(self) -> None:
        template = _load_prompt_template("highlight")
        message = build_highlight_messages("1\t香港", subtitle_theme="white")[0]
        self.assertEqual(message["role"], "user")
        self.assertTrue(message["content"].startswith(template))
        self.assertNotIn("渲染主题固定为", message["content"])
        self.assertIn("1\t香港", message["content"])


if __name__ == "__main__":
    unittest.main()
