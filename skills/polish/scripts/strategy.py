from __future__ import annotations

from typing import Any

TASK = 'polish'


def _normalize_line_text(text: str) -> str:
    value = (text or '').strip()
    if value.endswith(("？", "?")):
        return value
    while value and value[-1] in '，。、；：!！.':
        value = value[:-1].rstrip()
    return value


def build_messages(system_prompt: str, request: Any) -> list[dict[str, str]]:
    kept = [line for line in request.lines if not bool(line.get('user_final_remove', False))]
    rows = [f"[L{int(line['line_id']):04d}] KEEP original={str(line.get('original_text') or '').strip()} current={str(line.get('optimized_text') or '').strip()}" for line in kept]
    user = (
        "执行任务：polish。\n"
        "只输出 JSON。格式："
        '{"lines":[{"line_id":1,"text":"...","reason":"..."}]}\n'
        "规则：\n"
        "1. 只润色 KEEP 行，不删除，不分章。\n"
        "2. 不新增事实，不跨行合并。\n"
        "3. 除问句外去掉行尾标点。\n"
        "4. 必须覆盖全部 KEEP line_id。\n\n"
        + "输入行：\n"
        + "\n".join(rows)
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def validate_payload(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    items = payload.get('lines')
    if not isinstance(items, list):
        raise RuntimeError('polish output missing lines array')
    kept = [line for line in request.lines if not bool(line.get('user_final_remove', False))]
    expected_ids = [int(line['line_id']) for line in kept]
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        line_id = int(item.get('line_id'))
        text = _normalize_line_text(str(item.get('text') or '').strip())
        if not text:
            raise RuntimeError(f'polish text missing for line {line_id}')
        result.append({'line_id': line_id, 'text': text, 'reason': str(item.get('reason') or '').strip()})
        seen.add(line_id)
    if sorted(seen) != sorted(expected_ids):
        raise RuntimeError('polish output must cover all kept line ids exactly once')
    return {'lines': sorted(result, key=lambda item: int(item['line_id']))}


def materialize(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    polished_by_id = {int(item['line_id']): item for item in payload['lines']}
    lines: list[dict[str, Any]] = []
    for line in request.lines:
        line_id = int(line['line_id'])
        if bool(line.get('user_final_remove', False)):
            lines.append(dict(line))
            continue
        next_line = dict(line)
        next_line['optimized_text'] = polished_by_id[line_id]['text']
        lines.append(next_line)
    return {'lines': lines, 'debug': {'task': TASK, 'payload': payload}}
