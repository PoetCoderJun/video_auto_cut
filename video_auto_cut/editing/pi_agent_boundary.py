from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import llm_client as llm_utils
from .pi_agent_models import BoundaryReviewState, ChunkExecutionState


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


class PiAgentBoundaryReview:
    def __init__(self, llm_config: dict[str, Any], chat_completion_fn: Any | None = None) -> None:
        self.llm_config = llm_config
        self.chat_completion_fn = chat_completion_fn

    def build_boundary_review_prompt(
        self,
        previous_state: ChunkExecutionState,
        current_state: ChunkExecutionState,
    ) -> list[dict[str, str]]:
        overlap_ids = self._overlap_line_ids(previous_state, current_state)
        overlap_lines = self._serialize_overlap_lines(previous_state, current_state, overlap_ids)
        system = (
            "你是口播删改 PI agent 的 boundary skill。"
            "你只检查 chunk overlap 区域，判断前一个 chunk 里哪些旧行已被后一个 chunk 的后续表达覆盖。"
            "只输出需要删除的旧 line id。只输出 JSON，不要解释。"
        )
        user = (
            '输出格式：{"dropped_line_ids":[30],"reason":"..."}\n'
            "请检查 overlap：\n"
            f"{overlap_lines}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def run(
        self,
        previous_state: ChunkExecutionState,
        current_state: ChunkExecutionState,
    ) -> BoundaryReviewState:
        try:
            payload = self._run_json_prompt(
                self.build_boundary_review_prompt(previous_state, current_state)
            )
            dropped_line_ids = [int(line_id) for line_id in payload.get("dropped_line_ids") or []]
            reason = str(payload.get("reason") or "").strip()
        except Exception as exc:
            logging.warning(
                "Boundary review JSON parse failed; keeping overlap decisions unchanged: %s",
                exc,
            )
            dropped_line_ids = []
            reason = "解析失败回退"
        return BoundaryReviewState(
            previous_chunk_id=previous_state.window.chunk_id,
            current_chunk_id=current_state.window.chunk_id,
            dropped_line_ids=dropped_line_ids,
            reason=reason,
        )

    def _run_json_prompt(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        chat_completion_fn = self.chat_completion_fn or llm_utils.chat_completion
        response = chat_completion_fn(self.llm_config, messages)
        return _json_loads(response)

    def _overlap_line_ids(
        self,
        previous_state: ChunkExecutionState,
        current_state: ChunkExecutionState,
    ) -> list[int]:
        previous_ids = {decision.line_id for decision in previous_state.decisions}
        current_ids = {decision.line_id for decision in current_state.decisions}
        return sorted(previous_ids & current_ids)

    def _serialize_overlap_lines(
        self,
        previous_state: ChunkExecutionState,
        current_state: ChunkExecutionState,
        overlap_ids: list[int],
    ) -> str:
        previous_map = {decision.line_id: decision for decision in previous_state.decisions}
        current_map = {decision.line_id: decision for decision in current_state.decisions}
        lines: list[str] = []
        for line_id in overlap_ids:
            if line_id in previous_map:
                lines.append(f"[L{line_id:04d}] previous={previous_map[line_id].current_text}")
            if line_id in current_map:
                lines.append(f"[L{line_id:04d}] current={current_map[line_id].current_text}")
        return "\n".join(lines)


def apply_boundary_review(
    previous_state: ChunkExecutionState,
    current_state: ChunkExecutionState,
    review: BoundaryReviewState,
) -> tuple[ChunkExecutionState, ChunkExecutionState]:
    dropped = set(review.dropped_line_ids)

    next_previous = ChunkExecutionState(
        window=previous_state.window,
        decisions=[
            decision for decision in previous_state.decisions if decision.line_id not in dropped
        ],
        merged_groups=[
            group
            for group in previous_state.merged_groups
            if not any(line_id in dropped for line_id in group.source_line_ids)
        ],
        core_line_ids=list(previous_state.core_line_ids),
    )
    next_current = ChunkExecutionState(
        window=current_state.window,
        decisions=list(current_state.decisions),
        merged_groups=list(current_state.merged_groups),
        core_line_ids=list(current_state.core_line_ids),
    )
    return next_previous, next_current
