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


def _normalize_legacy_prompt_doc(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        if line.startswith("> "):
            continue
        cleaned_lines.append(line.rstrip())
    normalized = "\n".join(cleaned_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


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
        return _normalize_legacy_prompt_doc(text)

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


def _append_runtime_note(prompt: str, note: str) -> str:
    note = str(note or "").strip()
    if not note:
        return re.sub(r"\n{3,}", "\n\n", prompt).strip()
    return re.sub(r"\n{3,}", "\n\n", f"{prompt.rstrip()}\n\n{note}").strip()


def _render_chapter_prompt(
    *,
    title_max_chars: int,
    max_chapters: int | None,
    chapter_policy_hint: str,
) -> str:
    prompt = _load_prompt_template("chapter")
    extra_rules: list[str] = []
    if max_chapters is not None and int(max_chapters) > 0:
        if chapter_policy_hint:
            max_chapters_rule = f"- 当前按{chapter_policy_hint}处理，本次最多只能分成 {int(max_chapters)} 章。"
        else:
            max_chapters_rule = f"- 本次最多只能分成 {int(max_chapters)} 章。"
        if "{{MAX_CHAPTERS_RULE}}" in prompt:
            prompt = prompt.replace("{{MAX_CHAPTERS_RULE}}", max_chapters_rule)
        else:
            extra_rules.append(max_chapters_rule)
    elif "{{MAX_CHAPTERS_RULE}}" in prompt:
        prompt = prompt.replace("{{MAX_CHAPTERS_RULE}}", "")

    title_limit = str(min(5, int(title_max_chars)))
    if "{{TITLE_MAX_CHARS}}" in prompt:
        prompt = prompt.replace("{{TITLE_MAX_CHARS}}", title_limit)
    else:
        extra_rules.append(f"- 标题绝不能超过 {title_limit} 个字。")

    prompt = re.sub(r"\n{3,}", "\n\n", prompt).strip()
    return _append_runtime_note(prompt, "\n".join(extra_rules))


def _build_user_message(*, prompt: str, instruction: str, payload: str) -> list[dict[str, str]]:
    content = "\n\n".join(
        part.strip()
        for part in [prompt, instruction, str(payload or "").strip()]
        if str(part or "").strip()
    ).strip()
    return [{"role": "user", "content": content}]


def build_delete_messages(timed_text: str) -> list[dict[str, str]]:
    return _build_user_message(
        prompt=_render_prompt_template("delete"),
        instruction="请直接处理下面的 delete 输入，并只输出要删除的行号：",
        payload=timed_text,
    )


def build_polish_messages(timed_text: str) -> list[dict[str, str]]:
    return _build_user_message(
        prompt=_render_prompt_template("polish"),
        instruction="请直接处理下面的 polish 输入，并只输出改动的行：",
        payload=timed_text,
    )


def build_chapter_messages(
    block_text: str,
    *,
    title_max_chars: int,
    max_chapters: int | None = None,
    chapter_policy_hint: str = "",
) -> list[dict[str, str]]:
    return _build_user_message(
        prompt=_render_chapter_prompt(
            title_max_chars=title_max_chars,
            max_chapters=max_chapters,
            chapter_policy_hint=chapter_policy_hint,
        ),
        instruction="请直接处理下面的 chapter 输入，并只输出最终章节文本：",
        payload=block_text,
    )


def build_highlight_messages(sparse_text: str, *, subtitle_theme: str) -> list[dict[str, str]]:
    theme_note = f"额外说明：渲染主题固定为 `{subtitle_theme}`，你无需输出主题信息。"
    prompt = _load_prompt_template("highlight")
    if "{{SUBTITLE_THEME_NOTE}}" in prompt:
        prompt = _render_prompt_template(
            "highlight",
            SUBTITLE_THEME_NOTE=theme_note,
        )
    else:
        prompt = _append_runtime_note(prompt, theme_note)
    return _build_user_message(
        prompt=prompt,
        instruction="请直接处理下面的 highlight 输入，并只输出需要高亮的行：",
        payload=sparse_text,
    )


def summarize_prompt_variant(task: str) -> dict[str, Any]:
    return {
        "task": str(task or "").strip(),
        "mode": "direct-prompt",
        "source": "skills/direct-prompts",
    }
