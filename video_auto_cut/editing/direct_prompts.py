# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIRECT_PROMPTS_DIR = PROJECT_ROOT / "skills" / "direct-prompts"
SYSTEM_PROMPT_START = "<!-- SYSTEM_PROMPT:START -->"
SYSTEM_PROMPT_END = "<!-- SYSTEM_PROMPT:END -->"


@lru_cache(maxsize=None)
def _load_prompt_template(name: str) -> str:
    path = DIRECT_PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise RuntimeError(f"Direct prompt source file missing: {path}")

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(SYSTEM_PROMPT_START)}\n?(.*?){re.escape(SYSTEM_PROMPT_END)}",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise RuntimeError(f"Direct prompt source file missing system prompt markers: {path}")

    prompt = match.group(1).strip()
    if not prompt:
        raise RuntimeError(f"Direct prompt source file has empty system prompt: {path}")
    return prompt


def _render_prompt_template(name: str, **replacements: str) -> str:
    prompt = _load_prompt_template(name)
    for key, value in replacements.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    unresolved = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", prompt)))
    if unresolved:
        raise RuntimeError(
            f"Direct prompt template still has unresolved placeholders for {name}: {', '.join(unresolved)}"
        )
    return re.sub(r"\n{3,}", "\n\n", prompt).strip()


def _render_chapter_system_prompt(
    *,
    title_max_chars: int,
    max_chapters: int | None,
    chapter_policy_hint: str,
) -> str:
    max_chapters_rule = ""
    if max_chapters is not None and int(max_chapters) > 0:
        if chapter_policy_hint:
            max_chapters_rule = f"- 当前按{chapter_policy_hint}处理，本次最多只能分成 {int(max_chapters)} 章。"
        else:
            max_chapters_rule = f"- 本次最多只能分成 {int(max_chapters)} 章。"
    return _render_prompt_template(
        "chapter",
        MAX_CHAPTERS_RULE=max_chapters_rule,
        TITLE_MAX_CHARS=str(min(5, int(title_max_chars))),
    )


def build_delete_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": _render_prompt_template("delete"),
        },
        {
            "role": "user",
            "content": "请直接处理下面的 delete 输入，并只输出要删除的行号：\n\n" + timed_text.strip(),
        },
    ]


def build_polish_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": _render_prompt_template("polish"),
        },
        {
            "role": "user",
            "content": "请直接处理下面的 polish 输入，并只输出改动的行：\n\n" + timed_text.strip(),
        },
    ]


def build_chapter_messages(
    block_text: str,
    *,
    title_max_chars: int,
    max_chapters: int | None = None,
    chapter_policy_hint: str = "",
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": _render_chapter_system_prompt(
                title_max_chars=title_max_chars,
                max_chapters=max_chapters,
                chapter_policy_hint=chapter_policy_hint,
            ),
        },
        {
            "role": "user",
            "content": "请直接处理下面的 chapter 输入，并只输出最终章节文本：\n\n" + block_text.strip(),
        },
    ]


def build_highlight_messages(sparse_text: str, *, subtitle_theme: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": _render_prompt_template(
                "highlight",
                SUBTITLE_THEME_NOTE=f"额外说明：渲染主题固定为 `{subtitle_theme}`，你无需输出主题信息。",
            ),
        },
        {
            "role": "user",
            "content": sparse_text.strip(),
        },
    ]


def summarize_prompt_variant(task: str) -> dict[str, Any]:
    return {
        "task": str(task or "").strip(),
        "mode": "direct-prompt",
        "source": "skills/direct-prompts",
    }
