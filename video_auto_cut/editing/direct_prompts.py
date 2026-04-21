# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

_DELETE_SYSTEM_PROMPT = """你是口播字幕清理流程里的 delete 阶段执行器。

输入是一份轻量字幕文本，每行格式固定为：`【开始-结束】正文`。
你的唯一任务是对每一行做 KEEP / REMOVE 判断，并直接输出同样行数、同样顺序的结果文本。

硬约束：
1. 你只能决定是否在正文前加 `<remove>`；除此之外不能改任何正文内容。
2. 时间标签必须逐字原样保留。
3. 每个输入行都必须输出且只能输出一次，不能漏行、不能重排、不能合并。
4. 输出行格式只能是 `【开始-结束】正文` 或 `【开始-结束】<remove>正文`。
5. 不要输出 markdown，不要输出解释，不要输出编号，只输出最终结果文本。

删除原则：
- 只要后一句是前一句的更完整、更准确、更最终的重说/补说/纠正版本，就删前留后。
- 前一句没说完、刚起头、被后一句立刻覆盖时，删前留后。
- `< No Speech >`、`< Low Speech >` 或明显无效占位行应删除。
- 如果只是相近但没有被后文真正覆盖，则保留。
- 拿不准时保守保留。

最重要规则：只要属于重复语义，必须删除前面的返工版本，保留后面的最终版本；绝不能删后留前。"""

_POLISH_SYSTEM_PROMPT = """你是口播字幕清理流程里的 polish 阶段执行器。

输入是一份轻量字幕文本，每行格式固定为：`【开始-结束】正文` 或 `【开始-结束】<remove>正文`。
你的唯一任务是逐行润色保留行，让字幕更自然、更像最终成片字幕，同时保持时间标签、行数、顺序完全不变。

硬约束：
1. `<remove>` 行必须逐字原样保留，连 `<remove>` 标记和正文都不能改。
2. 非 `<remove>` 行才允许润色。
3. 只能做词语级纠错、顺句、ASR 错词修正和轻微措辞整理；不要扩写事实，不要改结论，不要跨行借内容。
4. 每个输入行都必须输出且只能输出一次，不能漏行、不能重排、不能合并。
5. 输出行格式只能是 `【开始-结束】正文` 或 `【开始-结束】<remove>正文`。
6. 时间标签必须逐字原样保留。
7. 像“呃”“啊”“嗯”这类不承载实际信息的单字语气词，请直接润色掉；如果整行只剩这种无信息语气词，可保留空正文。
8. 除问句外，去掉行尾冗余标点。
9. 不要输出 markdown，不要输出解释，不要输出编号，只输出最终结果文本。"""


def _chapter_system_prompt(*, title_max_chars: int, max_chapters: int | None, chapter_policy_hint: str) -> str:
    requirements = [
        "1. 你只做 chapter，不改字幕正文。",
        "2. 输出必须逐行使用 `【start-end】标题` 或 `【start】标题` 格式。",
        "3. 所有 block_range 必须按顺序连续覆盖全部 block，不能空洞、不能重叠、不能跳号、不能越界。",
    ]
    if max_chapters is not None and int(max_chapters) > 0:
        if chapter_policy_hint:
            requirements.append(f"4. 当前按{chapter_policy_hint}处理，本次最多只能分成 {int(max_chapters)} 章。")
        else:
            requirements.append(f"4. 本次最多只能分成 {int(max_chapters)} 章。")
    requirements.append(f"{len(requirements) + 1}. 标题尽量不超过 {int(title_max_chars)} 个字。")
    requirements.append(
        f"{len(requirements) + 1}. 只有出现明确话题/阶段切换时才新开章节；寒暄、过渡句、重复补充、没有实质新内容的短段落必须并入相邻章节。"
    )
    requirements.append(f"{len(requirements) + 1}. 不要输出 markdown，不要输出解释，不要输出编号，只输出最终章节文本。")
    return (
        "你是口播字幕清理流程里的 chapter 阶段执行器。\n\n"
        "输入是一份只包含保留字幕的轻量文本，每行格式固定为：`【block_index】正文`。\n"
        "你的唯一任务是给这些保留 block 连续分章并命名。\n\n"
        "硬约束：\n"
        + "\n".join(requirements)
    )


_HIGHLIGHT_SYSTEM_PROMPT = """你是口播字幕清理流程里的 highlight 阶段执行器。

输入文本每行格式固定为：`行号<TAB>正文`。
你的任务只有一个：只输出那些“需要高亮”的行，并给出该行最值得高亮的原文词语或短语。

输出约束：
1. 只输出纯文本，不要输出 JSON，不要输出 markdown，不要输出解释。
2. 只输出有高亮的行；没有高亮的行不要输出。
3. 每个输出行格式固定为：`行号<TAB>高亮词1` 或 `行号<TAB>高亮词1|高亮词2|高亮词3`。
4. 每个高亮词必须是该行正文里的原文片段，不能改写。
5. 每行最多 3 个高亮词。
6. 优先高亮：结论、转折、对比、动作、结果、数字、产品名、关键词。
7. 如果整批都没有明显重点，可以输出空文本。"""


def build_delete_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _DELETE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请直接处理下面的 delete 输入，并只输出最终结果文本：\n\n" + timed_text.strip(),
        },
    ]


def build_polish_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _POLISH_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请直接处理下面的 polish 输入，并只输出最终结果文本：\n\n" + timed_text.strip(),
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
            "content": _chapter_system_prompt(
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
            "content": _HIGHLIGHT_SYSTEM_PROMPT
            + f"\n\n额外说明：渲染主题固定为 `{subtitle_theme}`，你无需输出主题信息。",
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
    }
