from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from . import llm_client as llm_utils
from .pi_agent_models import LineDecision


@dataclass(frozen=True)
class RemoveLoopResult:
    decisions: list[LineDecision]
    debug: dict[str, Any]


TRAILING_COMMA_RE = re.compile(r",(?=\s*[}\]])")


def _strip_code_fence(text: str) -> str:
    value = (text or "").strip()
    if "```" not in value:
        return value
    parts = value.split("```")
    if len(parts) >= 3:
        return parts[1].strip()
    return value


def _json_loads(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()

    candidates: list[str] = []
    for candidate in (cleaned, _extract_json_object(cleaned), _sanitize_json_like(cleaned)):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    extracted = _extract_json_object(cleaned)
    if extracted:
        sanitized_extracted = _sanitize_json_like(extracted)
        if sanitized_extracted and sanitized_extracted not in candidates:
            candidates.append(sanitized_extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            raise ValueError("LLM output must be a JSON object")
        return payload

    preview = cleaned[:400].replace("\n", "\\n")
    raise ValueError(f"Failed to parse LLM JSON payload: {preview}") from last_error


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return ""
    return text[start : end + 1].strip()


def _sanitize_json_like(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value
    return TRAILING_COMMA_RE.sub("", value)


def _segments_to_tagged_text(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for segment in segments:
        line_id = int(segment.get("id") or 0)
        text = str(segment.get("text") or "").strip()
        lines.append(f"[L{line_id:04d}] {text}")
    return "\n".join(lines)


class PiAgentRemoveLoop:
    def __init__(
        self,
        llm_config: dict[str, Any],
        chat_completion_fn: Any | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.chat_completion_fn = chat_completion_fn

    def build_remove_inspect_prompt(
        self, segments: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        tagged_text = _segments_to_tagged_text(segments)
        system = (
            "你是口播删改 PI agent 的 remove skill。"
            "任务只有一个：如果后面的行重新表达了前面已经说过的语义，就把前面重复的那部分删掉。"
            "按时间从后往前看，只处理前文被后文覆盖的重复部分。"
            "不要因为重要性、流畅度、卖点、语气而删句。"
            "如果一行只有一部分被后文覆盖，就保留未重复的部分；只有整行都被后文覆盖时，才整行删除。"
            "只输出 JSON，不要解释。"
        )
        user = (
            "请检查下面这些相邻字幕行，并给出每一行删重后的结果。\n"
            "输出格式："
            '{"decisions":[{"line_id":8,"action":"KEEP","edited_text":"保留删重后的文本","reason":"...","confidence":0.95}]}\n'
            "如果整行都应删除，action=REMOVE，edited_text 设为空字符串。"
            "如果只删掉行内重复片段，action=KEEP，并输出删重后的 edited_text。"
            "原文：\n"
            f"{tagged_text}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def run(self, segments: list[dict[str, Any]]) -> RemoveLoopResult:
        if not segments:
            return RemoveLoopResult(decisions=[], debug={"iterations": 0, "final_source": "empty"})

        try:
            draft_payload = self._run_json_prompt(self.build_remove_inspect_prompt(segments))
            final_source = "draft"
            error = None
        except Exception as exc:
            logging.warning(
                "Remove agent JSON parse failed; falling back to KEEP for %d lines: %s",
                len(segments),
                exc,
            )
            draft_payload = self._build_keep_payload(segments, reason="解析失败回退")
            final_source = "parse_fallback"
            error = str(exc)

        decisions = self._build_line_decisions(segments, draft_payload, draft_payload, final_source)
        return RemoveLoopResult(
            decisions=decisions,
            debug={
                "iterations": 1,
                "draft": draft_payload,
                "critique": None,
                "final": draft_payload,
                "final_source": final_source,
                "error": error,
            },
        )

    def _run_json_prompt(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        chat_completion_fn = self.chat_completion_fn or llm_utils.chat_completion
        response = chat_completion_fn(self.llm_config, messages)
        return _json_loads(response)

    def _build_line_decisions(
        self,
        segments: list[dict[str, Any]],
        draft_payload: dict[str, Any],
        final_payload: dict[str, Any],
        final_source: str,
    ) -> list[LineDecision]:
        draft_map = self._payload_to_map(draft_payload)
        final_map = self._payload_to_map(final_payload)
        use_final = final_source != "fallback"

        decisions: list[LineDecision] = []
        for segment in segments:
            line_id = int(segment.get("id") or 0)
            payload = final_map.get(line_id) if use_final else draft_map.get(line_id)
            if payload is None:
                payload = draft_map.get(line_id) or {
                    "line_id": line_id,
                    "action": "KEEP",
                    "edited_text": str(segment.get("text") or "").strip(),
                    "reason": "缺失回退",
                    "confidence": 0.0,
                }
            original_text = str(segment.get("text") or "").strip()
            edited_text = str(payload.get("edited_text") or "").strip()
            action = str(payload.get("action") or "KEEP").upper()
            current_text = edited_text or original_text
            if action == "REMOVE" and edited_text:
                current_text = edited_text
            decisions.append(
                LineDecision(
                    line_id=line_id,
                    original_text=original_text,
                    current_text=current_text,
                    remove_action=action,
                    reason=str(payload.get("reason") or "").strip(),
                    confidence=float(payload.get("confidence") or 0.0),
                )
            )
        return decisions

    def _payload_to_map(self, payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
        items = payload.get("decisions") or []
        result: dict[int, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                line_id = int(item.get("line_id"))
            except (TypeError, ValueError):
                continue
            result[line_id] = item
        return result

    def _build_keep_payload(
        self,
        segments: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "line_id": int(segment.get("id") or 0),
                    "action": "KEEP",
                    "edited_text": str(segment.get("text") or "").strip(),
                    "reason": reason,
                    "confidence": 0.0,
                }
                for segment in segments
            ]
        }
