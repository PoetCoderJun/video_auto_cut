from __future__ import annotations

from typing import Any

from .pi_agent_models import LineDecision, MergedGroup


TRAILING_LINE_PUNCTUATION = "，。、；：!！"
JOIN_PUNCTUATION = set("，、；：,.!?！？。")


def _normalize_line_text(text: str) -> str:
    value = (text or "").strip()
    while value and value[-1] in TRAILING_LINE_PUNCTUATION:
        value = value[:-1].rstrip()
    return value


def _join_text(left: str, right: str) -> str:
    left_text = _normalize_line_text(left)
    right_text = _normalize_line_text(right)
    if not left_text:
        return right_text
    if not right_text:
        return left_text
    if left_text.endswith(("？", "?")):
        if right_text[:1] in JOIN_PUNCTUATION:
            return left_text + right_text[1:].lstrip()
        return left_text + right_text
    return left_text + "，" + right_text


def build_merged_groups(
    segments: list[dict[str, Any]],
    decisions: list[LineDecision],
    threshold: int,
) -> list[MergedGroup]:
    if not segments or not decisions:
        return []

    decision_map = {decision.line_id: decision for decision in decisions}
    groups: list[MergedGroup] = []
    index = 0
    total = len(segments)

    while index < total:
        segment = segments[index]
        line_id = int(segment.get("id") or 0)
        decision = decision_map.get(line_id)
        if decision is None or decision.remove_action != "KEEP":
            index += 1
            continue

        merged_text = decision.current_text.strip()
        merged_start = float(segment.get("start") or 0.0)
        merged_end = float(segment.get("end") or 0.0)
        source_line_ids = [line_id]

        if len(merged_text) >= threshold:
            groups.append(
                MergedGroup(
                    source_line_ids=source_line_ids,
                    text=merged_text,
                    start=merged_start,
                    end=merged_end,
                )
            )
            index += 1
            continue

        next_index = index + 1
        while next_index < total:
            next_segment = segments[next_index]
            next_line_id = int(next_segment.get("id") or 0)
            next_decision = decision_map.get(next_line_id)
            if next_decision is None:
                next_index += 1
                continue
            if next_decision.remove_action != "KEEP":
                break
            merged_text = _join_text(merged_text, next_decision.current_text)
            merged_start = min(merged_start, float(next_segment.get("start") or 0.0))
            merged_end = max(merged_end, float(next_segment.get("end") or 0.0))
            source_line_ids.append(next_line_id)
            next_index += 1
            if len(merged_text) >= threshold:
                break

        groups.append(
            MergedGroup(
                source_line_ids=source_line_ids,
                text=merged_text,
                start=merged_start,
                end=merged_end,
            )
        )
        index = next_index

    return groups
