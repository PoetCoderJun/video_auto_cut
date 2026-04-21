# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

_DELETE_SYSTEM_PROMPT = """你是口播字幕清理流程里的 delete 阶段执行器。

输入文本每行格式固定为：`行号<TAB>正文`。
你的唯一任务是判断哪些行应该删除，并只输出“要删除的行号”。

硬约束：
1. 只输出需要删除的行号；保留行不要输出。
2. 每个输出行格式固定为：`行号`。
3. 不要输出正文，不要输出 `<remove>`，不要输出 markdown，不要输出解释。
4. 如果没有任何行需要删除，可以输出空文本。
5. 只能删除整行，不能改写正文。

删除原则：
- 只要后一句是前一句的更完整、更准确、更最终的重说/补说/纠正版本，就删前留后。
- 前一句没说完、刚起头、被后一句立刻覆盖时，删前留后。
- `< No Speech >`、`< Low Speech >` 或明显无效占位行应删除。
- 如果只是相近但没有被后文真正覆盖，则保留。
- 拿不准时保守保留。

经验判断（这是最重要的实战经验）：
- 不要只看字面相同，要看“是不是在说同一件事”。即使措辞不同、词没完全重合，只要主语/对象/动作/结论明显还是同一个，就按重复语义处理。
- 口播返工常见形态是：前一句先起头，后一句马上换个更完整的说法重讲。前一句往往更短、更乱、更像半成品；后一句往往信息更完整、句子更顺、关键词更准确。这种情况基本都删前留后。
- 如果连续几句都围绕同一个命题推进，且后一句已经把前一句的意思完整覆盖，前一句就该删；不要因为前一句“也像完整句”就保留它。
- 当前一句只有框架词、起手词、口头过渡词（例如“首先”“就是”“如果你不是…”的起头半句），而后一句才把真正结论说完整，这种前句通常是返工残片，应删除。
- 如果后一句修正了前一句里的数字、专有名词、英文词、政策术语、关系判断或关键结论，要默认后一句才是最终版本；前一句即使不完全一样，也通常应删。
- 对相邻 2 到 4 行要主动做“前后对照”：问自己“如果只保留后一句，用户想表达的信息是否已经都在？”如果答案是“是”，前一句就删。
- 如果一个返工簇里出现了两次以上相似起手句/铺垫句（例如两次“哪怕事先写了稿 / 哪怕提前写了稿”、两次“其他人做过类似工具 / 其他人做的类似工具”），通常应优先保留最后一版、最靠近完整结论的一版，前面的铺垫版大多要删。
- 如果某个短前句本身不能独立成立，只有和后面的长句拼起来才像完整表达，那么要进一步检查：后面是否已经自己重新起头并给出更完整版本。若是，前面的短前句也应删，不要把更早的铺垫残留在最终稿里。
- 当你在“删前面”还是“删后面”之间犹豫时，优先保留最晚出现、最完整、最顺、关键词最准确的那一版。
- 宁可把明显返工残句删掉，也不要把前后两个语义重复版本都留下来。

最重要规则：只要属于重复语义，必须删除前面的返工版本，保留后面的最终版本；绝不能删后留前。"""

_POLISH_SYSTEM_PROMPT = """你是口播字幕清理流程里的 polish 阶段执行器。

输入文本每行格式固定为：`行号<TAB>正文`，并且只包含当前保留行。
你的唯一任务是只输出那些“需要改写”的行；没变化的行不要输出。

硬约束：
1. 只输出需要改动的行；未改动的行不要输出。
2. 每个输出行格式固定为：`行号<TAB>改后正文`。
3. 如果某行应被清空/删除（例如整行只是“嗯/啊/呃”这类无信息语气词），输出：`行号<TAB><empty>`。
4. 只能做词语级纠错、顺句、ASR 错词修正和轻微措辞整理；尤其要主动修复明显的 ASR 错词、同音误识别、英文/专有名词误识别。对明显可疑的英文词、中英夹杂怪词、音近错词不要保守照抄，能结合上下文修正就修正；如果英文原词拿不准，也优先改成自然、准确的中文说法。不要扩写事实，不要改结论，不要跨行借内容。
5. 每行最多对应一个输出行，不能重复输出同一行号。
6. 不要输出 markdown，不要输出解释，不要输出未修改的行。
7. 除问句外，去掉行尾冗余标点。"""


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
        f"{len(requirements) + 1}. 只有出现明确话题/阶段切换时才新开章节；寒暄、过渡句、重复补充、没有实质新内容的短段落必须并入相邻章节。没有必要时宁少勿多，优先合并而不是拆碎。"
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
3. 每个输出行格式固定为：`行号<TAB>高亮词1` 或 `行号<TAB>高亮词1|高亮词2`。
4. 每个高亮词必须是该行正文里的原文片段，不能改写。
5. 每行最多 2 个高亮词，而且优先只给 1 个。
6. 只高亮少量真正关键的词，不要高亮整句、长短语、普通修饰词、礼貌词或上下文已经明显的内容。
7. 优先高亮：数字、专有名词、政策关键词、强结论词、强对比词、动作结果词。
8. 如果没有明显值得强调的关键词，就不要输出该行。"""


def build_delete_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _DELETE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "请直接处理下面的 delete 输入，并只输出要删除的行号：\n\n" + timed_text.strip(),
        },
    ]


def build_polish_messages(timed_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _POLISH_SYSTEM_PROMPT},
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
