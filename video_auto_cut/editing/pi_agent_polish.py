from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import llm_client as llm_utils
from .pi_agent_models import LineDecision


TRAILING_LINE_PUNCTUATION = "，。、；：!！."


@dataclass(frozen=True)
class PolishLoopResult:
    decisions: list[LineDecision]
    debug: dict[str, Any]


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
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("LLM output must be a JSON object")
    return payload


def _normalize_polished_text(text: str) -> str:
    value = (text or "").strip()
    if value.endswith(("？", "?")):
        return value
    while value and value[-1] in TRAILING_LINE_PUNCTUATION:
        value = value[:-1].rstrip()
    return value


class PiAgentPolishLoop:
    def __init__(
        self,
        llm_config: dict[str, Any],
        max_iterations: int = 2,
        chat_completion_fn: Any | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.max_iterations = max_iterations
        self.chat_completion_fn = chat_completion_fn

    def build_polish_draft_prompt(
        self,
        decisions: list[LineDecision],
    ) -> list[dict[str, str]]:
        system = (
            "你是口播润色 PI agent 的 polish skill。"
            "任务：只润色保留行，让每一行更像最终口播会说出来的话。"
            "不要跨行合并，不要删除，不要新增信息。"
            "修正明显 ASR 错字，去掉口头语和拖沓重复。"
            "除问句外，行尾不要标点。只输出 JSON，不要解释。"
        )
        user = (
            "请逐行润色这些字幕。\n"
            '输出格式：{"lines":[{"line_id":8,"text":"...","reason":"...","confidence":0.95}]}\n'
            "lines:\n"
            f"{self._serialize_decisions(decisions)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def build_polish_critique_prompt(
        self,
        decisions: list[LineDecision],
        draft_payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        system = (
            "你是口播润色 PI agent 的 critique skill。"
            "检查逐行润色结果是否保留了错字、口头语、重复拖沓，或出现了过度改写。"
            "不要从跨行合并角度提建议。只输出 JSON，不要解释。"
        )
        user = (
            "请审查这份逐行 polish draft。\n"
            '输出格式：{"needs_revision":true,"issues":[{"line_id":8,"message":"..."}]}\n'
            "source lines:\n"
            f"{self._serialize_decisions(decisions)}\n\n"
            "draft:\n"
            f"{json.dumps(draft_payload, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def build_polish_revise_prompt(
        self,
        decisions: list[LineDecision],
        draft_payload: dict[str, Any],
        critique_payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        system = (
            "你是口播润色 PI agent 的 revise skill。"
            "根据 critique 修正逐行 polish draft。必须覆盖全部保留行。"
            "不要跨行合并。只输出 JSON，不要解释。"
        )
        user = (
            "请根据 critique 重新给出完整的逐行润色结果。\n"
            '输出格式：{"lines":[{"line_id":8,"text":"...","reason":"...","confidence":0.95}]}\n'
            "source lines:\n"
            f"{self._serialize_decisions(decisions)}\n\n"
            "draft:\n"
            f"{json.dumps(draft_payload, ensure_ascii=False)}\n\n"
            "critique:\n"
            f"{json.dumps(critique_payload, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def run(self, decisions: list[LineDecision]) -> PolishLoopResult:
        keep_decisions = [decision for decision in decisions if decision.remove_action == "KEEP"]
        if not keep_decisions:
            return PolishLoopResult(decisions=list(decisions), debug={"iterations": 0, "final_source": "empty"})

        draft_payload = self._run_json_prompt(self.build_polish_draft_prompt(keep_decisions))
        final_payload = draft_payload
        final_source = "draft"
        critique_payload: dict[str, Any] = {"needs_revision": False, "issues": []}
        iterations = 0

        for _ in range(self.max_iterations):
            iterations += 1
            critique_payload = self._run_json_prompt(
                self.build_polish_critique_prompt(keep_decisions, final_payload)
            )
            if not bool(critique_payload.get("needs_revision")):
                break

            revised_payload = self._run_json_prompt(
                self.build_polish_revise_prompt(keep_decisions, final_payload, critique_payload)
            )
            if self._covers_all_lines(revised_payload, keep_decisions):
                final_payload = revised_payload
                final_source = "revise"
                break
            final_source = "fallback"
            break

        polished = self._build_decisions(decisions, draft_payload, final_payload, final_source)
        return PolishLoopResult(
            decisions=polished,
            debug={
                "iterations": iterations,
                "draft": draft_payload,
                "critique": critique_payload,
                "final": final_payload,
                "final_source": final_source,
            },
        )

    def _serialize_decisions(self, decisions: list[LineDecision]) -> str:
        return "\n".join(
            f"[L{decision.line_id:04d}] original={decision.original_text} current={decision.current_text}"
            for decision in decisions
        )

    def _run_json_prompt(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        chat_completion_fn = self.chat_completion_fn or llm_utils.chat_completion
        response = chat_completion_fn(self.llm_config, messages)
        return _json_loads(response)

    def _covers_all_lines(self, payload: dict[str, Any], decisions: list[LineDecision]) -> bool:
        items = payload.get("lines")
        if not isinstance(items, list):
            return False
        expected = {decision.line_id for decision in decisions}
        seen: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                return False
            try:
                line_id = int(item.get("line_id"))
            except (TypeError, ValueError):
                return False
            if not str(item.get("text") or "").strip():
                return False
            seen.add(line_id)
        return seen == expected

    def _build_decisions(
        self,
        decisions: list[LineDecision],
        draft_payload: dict[str, Any],
        final_payload: dict[str, Any],
        final_source: str,
    ) -> list[LineDecision]:
        draft_map = self._payload_to_map(draft_payload)
        final_map = self._payload_to_map(final_payload)
        use_final = final_source != "fallback"
        polished: list[LineDecision] = []

        for decision in decisions:
            if decision.remove_action != "KEEP":
                polished.append(decision)
                continue
            payload = final_map.get(decision.line_id) if use_final else draft_map.get(decision.line_id)
            if payload is None:
                payload = draft_map.get(decision.line_id) or {"text": decision.current_text}
            polished.append(
                LineDecision(
                    line_id=decision.line_id,
                    original_text=decision.original_text,
                    current_text=_normalize_polished_text(str(payload.get("text") or decision.current_text)),
                    remove_action=decision.remove_action,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    source_line_ids=list(decision.source_line_ids),
                )
            )
        return polished

    def _payload_to_map(self, payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for item in payload.get("lines") or []:
            if not isinstance(item, dict):
                continue
            try:
                line_id = int(item.get("line_id"))
            except (TypeError, ValueError):
                continue
            result[line_id] = item
        return result
