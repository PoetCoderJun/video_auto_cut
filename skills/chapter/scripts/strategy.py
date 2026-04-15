from __future__ import annotations

from typing import Any

from video_auto_cut.editing.chapter_domain import canonicalize_step1_chapters, kept_step1_lines

TASK = 'chapter'


def build_messages(system_prompt: str, request: Any) -> list[dict[str, str]]:
    kept = kept_step1_lines(request.lines)
    rows = [f"[B{index:03d}] line_id={int(line['line_id'])} text={str(line.get('optimized_text') or line.get('original_text') or '').strip()}" for index, line in enumerate(kept, start=1)]
    user = (
        "执行任务：chapter。\n"
        "只输出 JSON。格式："
        '{"chapters":[{"chapter_id":1,"title":"开场","block_range":"1-3"}]}\n'
        "规则：\n"
        f"1. title 尽量不超过 {request.title_max_chars} 个字。\n"
        "2. 所有 block_range 必须连续覆盖全部保留字幕。\n"
        "3. 不允许空洞、重叠、跳号。\n"
        "4. 不要输出解释。\n\n"
        + "输入 block：\n"
        + "\n".join(rows)
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def validate_payload(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    items = payload.get('chapters')
    if not isinstance(items, list) or not items:
        raise RuntimeError('chapter output missing chapters array')
    normalized = canonicalize_step1_chapters(
        [
            {
                'chapter_id': int(item.get('chapter_id', index + 1)),
                'title': str(item.get('title') or '').strip(),
                'block_range': item.get('block_range'),
            }
            for index, item in enumerate(items)
            if isinstance(item, dict)
        ],
        kept_step1_lines(request.lines),
    )
    return {'chapters': normalized}


def materialize(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    return {'lines': list(request.lines), 'chapters': payload['chapters'], 'debug': {'task': TASK, 'payload': payload}}
