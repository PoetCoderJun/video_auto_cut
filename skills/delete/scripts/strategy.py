from __future__ import annotations

from typing import Any

TASK = 'delete'


def build_messages(system_prompt: str, request: Any) -> list[dict[str, str]]:
    segments = list(request.segments)
    rows = [f"[L{int(segment['id']):04d}] {str(segment.get('text') or '').strip()}" for segment in segments]
    user = (
        "执行任务：delete。\n"
        "只输出 JSON。格式："
        '{"lines":[{"line_id":1,"action":"KEEP","reason":"..."}]}\n'
        "规则：\n"
        "1. 只做删除判断，不润色，不分章。\n"
        "2. 如果后一句覆盖前一句语义，删除前一句。\n"
        "3. `< Low Speech >` 等无语音占位应删除。\n"
        "4. 必须覆盖全部 line_id。\n\n"
        + "输入字幕：\n"
        + "\n".join(rows)
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def validate_payload(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    items = payload.get("lines")
    if not isinstance(items, list):
        raise RuntimeError("delete output missing lines array")
    expected_ids = [int(segment["id"]) for segment in request.segments]
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        line_id = int(item.get("line_id"))
        action = str(item.get("action") or "").strip().upper()
        if action not in {"KEEP", "REMOVE"}:
            raise RuntimeError(f"delete action invalid for line {line_id}")
        result.append({"line_id": line_id, "action": action, "reason": str(item.get("reason") or "").strip()})
        seen.add(line_id)
    if sorted(seen) != sorted(expected_ids):
        raise RuntimeError("delete output must cover all line ids exactly once")
    return {"lines": sorted(result, key=lambda item: int(item["line_id"]))}


def materialize(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    action_by_id = {int(item["line_id"]): item for item in payload["lines"]}
    lines: list[dict[str, Any]] = []
    for segment in request.segments:
        line_id = int(segment["id"])
        action = action_by_id[line_id]["action"]
        original_text = str(segment.get("text") or "").strip()
        remove = action == "REMOVE" or original_text.strip().lower() in {"< low speech >", "<low speech>", "< no speech >", "<no speech>"}
        lines.append(
            {
                "line_id": line_id,
                "start": float(segment.get("start") or 0.0),
                "end": float(segment.get("end") or 0.0),
                "original_text": original_text,
                "optimized_text": original_text,
                "ai_suggest_remove": remove,
                "user_final_remove": remove,
            }
        )
    return {"lines": lines, "debug": {"task": TASK, "payload": payload}}
