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


def _normalize_prompt_doc(text: str) -> str:
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
        return _normalize_prompt_doc(text)

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


def _build_user_message(*, prompt: str, payload: str) -> list[dict[str, str]]:
    content = "\n\n".join(
        part.strip()
        for part in [prompt, str(payload or "").strip()]
        if str(part or "").strip()
    ).strip()
    return [{"role": "user", "content": content}]


def _build_input_payload(*, timed_text: str, script: str = "") -> str:
    body = str(timed_text or "").strip()
    reference_script = str(script or "").strip()
    if not reference_script:
        return body
    return "\n\n".join(
        [
            "## 参考口播脚本",
            reference_script,
            "## 待处理字幕",
            body,
        ]
    ).strip()


def build_delete_messages(timed_text: str, *, script: str = "") -> list[dict[str, str]]:
    prompt_name = "delete-with-reference" if str(script or "").strip() else "delete"
    return _build_user_message(
        prompt=_render_prompt_template(prompt_name),
        payload=_build_input_payload(timed_text=timed_text, script=script),
    )


def build_polish_messages(timed_text: str, *, script: str = "") -> list[dict[str, str]]:
    prompt_name = "polish-with-reference" if str(script or "").strip() else "polish"
    return _build_user_message(
        prompt=_render_prompt_template(prompt_name),
        payload=_build_input_payload(timed_text=timed_text, script=script),
    )


def build_chapter_messages(
    block_text: str,
    *,
    title_max_chars: int,
    max_chapters: int | None = None,
    chapter_policy_hint: str = "",
) -> list[dict[str, str]]:
    _ = (title_max_chars, max_chapters, chapter_policy_hint)
    return _build_user_message(
        prompt=_render_prompt_template("chapter"),
        payload=block_text,
    )


def build_highlight_messages(sparse_text: str, *, subtitle_theme: str) -> list[dict[str, str]]:
    _ = subtitle_theme
    return _build_user_message(
        prompt=_render_prompt_template("highlight"),
        payload=sparse_text,
    )


def summarize_prompt_variant(task: str) -> dict[str, Any]:
    return {
        "task": str(task or "").strip(),
        "mode": "direct-prompt",
        "source": "skills/direct-prompts",
    }
