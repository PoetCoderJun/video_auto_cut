from __future__ import annotations

import re
import unittest
from pathlib import Path

from video_auto_cut.editing.direct_prompts import (
    DIRECT_PROMPTS_DIR,
    SYSTEM_PROMPT_END,
    SYSTEM_PROMPT_START,
    build_chapter_messages,
    build_delete_messages,
    build_highlight_messages,
    build_polish_messages,
)


def _extract_runtime_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(SYSTEM_PROMPT_START)}\n?(.*?){re.escape(SYSTEM_PROMPT_END)}",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"missing runtime prompt markers in {path}")
    return match.group(1).strip()


class DirectPromptSourceOfTruthTests(unittest.TestCase):
    def test_delete_system_prompt_is_loaded_from_skills_direct_prompts(self) -> None:
        expected = _extract_runtime_prompt(DIRECT_PROMPTS_DIR / "delete.md")
        self.assertEqual(build_delete_messages("1\t第一句")[0]["content"], expected)

    def test_polish_system_prompt_is_loaded_from_skills_direct_prompts(self) -> None:
        expected = _extract_runtime_prompt(DIRECT_PROMPTS_DIR / "polish.md")
        self.assertEqual(build_polish_messages("1\t原句")[0]["content"], expected)

    def test_chapter_system_prompt_resolves_runtime_placeholders_from_skills_direct_prompts(self) -> None:
        template = _extract_runtime_prompt(DIRECT_PROMPTS_DIR / "chapter.md")
        expected = (
            template.replace("{{MAX_CHAPTERS_RULE}}", "- 当前按横屏视频章节约束处理，本次最多只能分成 2 章。")
            .replace("{{TITLE_MAX_CHARS}}", "5")
            .strip()
        )
        expected = re.sub(r"\n{3,}", "\n\n", expected)

        prompt = build_chapter_messages(
            "【1】第一段",
            title_max_chars=5,
            max_chapters=2,
            chapter_policy_hint="横屏视频章节约束",
        )[0]["content"]
        self.assertEqual(prompt, expected)

    def test_highlight_system_prompt_resolves_theme_note_from_skills_direct_prompts(self) -> None:
        template = _extract_runtime_prompt(DIRECT_PROMPTS_DIR / "highlight.md")
        expected = template.replace(
            "{{SUBTITLE_THEME_NOTE}}",
            "额外说明：渲染主题固定为 `white`，你无需输出主题信息。",
        ).strip()
        expected = re.sub(r"\n{3,}", "\n\n", expected)

        prompt = build_highlight_messages("1\t香港", subtitle_theme="white")[0]["content"]
        self.assertEqual(prompt, expected)


if __name__ == "__main__":
    unittest.main()
