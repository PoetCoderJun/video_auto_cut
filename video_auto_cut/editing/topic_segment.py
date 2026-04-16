from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import srt

from . import llm_client as llm_utils
from video_auto_cut.shared.interfaces import PipelineOptions
from video_auto_cut.shared.srt_parser import parse_decision_and_text


REMOVE_TOKEN = "<remove>"
SPACE_PATTERN = re.compile(r"\s+")
ID_RANGE_PATTERN = re.compile(r"^\s*(\d+)\s*(?:[-~—–到至]\s*(\d+)\s*)?$")
TOPIC_TITLE_MAX_CHARS_DEFAULT = 6
TOPIC_MAX_TOPICS_HARD_CAP = 6
TOPIC_SHORT_VIDEO_MAX_SECONDS = 150.0
TOPIC_LONG_VIDEO_MIN_SECONDS = 360.0
TOPIC_BLOCKS_PER_CHAPTER_TARGET = 3.5
TOPIC_BLOCK_MIN_SECONDS = 6.0
TOPIC_BLOCK_MAX_TARGET_SECONDS = 18.0
TOPIC_BLOCK_MAX_HARD_SECONDS = 24.0
TOPIC_BLOCK_MIN_CHARS = 28
TOPIC_BLOCK_MAX_TARGET_CHARS = 110
TOPIC_BLOCK_MAX_HARD_CHARS = 150
TOPIC_BLOCK_MIN_TAIL_RATIO = 0.6
TOPIC_MIN_SEGMENTS_PER_CHAPTER = 3


def _recommended_topic_budget(duration_s: float) -> int:
    normalized_duration = max(0.0, float(duration_s))
    if normalized_duration >= TOPIC_LONG_VIDEO_MIN_SECONDS:
        return 6
    if normalized_duration >= TOPIC_SHORT_VIDEO_MAX_SECONDS:
        return 5
    return 4


def _topic_count_range(duration_s: float) -> tuple[int, int, int]:
    recommended = _recommended_topic_budget(duration_s)
    min_topics = min(4, recommended)
    return min_topics, recommended, TOPIC_MAX_TOPICS_HARD_CAP


def _recommended_title_chars(title_max_chars: int) -> int:
    return max(1, min(5, int(title_max_chars)))


def _accepted_title_chars(title_max_chars: int) -> int:
    return max(6, int(title_max_chars))


@dataclass
class TopicSegment:
    segment_id: int
    start: float
    end: float
    text: str
    cue: Optional[str] = None


@dataclass
class TopicBlock:
    block_id: int
    segment_ids: List[int]
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TopicAgentLoopResult:
    payload: dict[str, Any]
    debug: dict[str, Any]


@dataclass(frozen=True)
class TopicBlockSpec:
    target_seconds: float
    max_seconds: float
    target_chars: int
    max_chars: int
    target_segments: int
    max_segments: int
    min_tail_seconds: float
    min_tail_chars: int
    min_tail_segments: int
    target_blocks: int
    pre_chunk_enabled: bool


class PiAgentTopicLoop:
    def __init__(
        self,
        llm_config: dict[str, Any],
        min_topics: int,
        max_topics: int,
        recommended_topics: int,
        title_max_chars: int,
        max_iterations: int = 5,
        strict: bool = False,
        chat_completion_fn: Optional[Any] = None,
    ) -> None:
        self.llm_config = llm_config
        self.min_topics = max(1, int(min_topics))
        self.max_topics = max(1, int(max_topics))
        self.recommended_topics = max(self.min_topics, min(int(recommended_topics), self.max_topics))
        self.title_max_chars = int(title_max_chars)
        self.strict = bool(strict)
        self.chat_completion_fn = chat_completion_fn

    def build_topic_draft_prompt(
        self,
        blocks: List["TopicBlock"],
        total_segments: int,
        min_topics: int,
        max_topics: int,
        recommended_topics: int,
        min_segments_per_topic: int,
    ) -> List[Dict[str, str]]:
        return _build_segmentation_prompt(
            blocks,
            total_segments,
            min_topics,
            max_topics,
            recommended_topics,
            self.title_max_chars,
            min_segments_per_topic,
        )

    def run(self, segments: List["TopicSegment"]) -> TopicAgentLoopResult:
        if not segments:
            raise RuntimeError("Topic segmentation requires non-empty segments.")

        blocks = _build_candidate_blocks(segments, self.recommended_topics)
        max_topics_by_segments = max(1, len(segments) // TOPIC_MIN_SEGMENTS_PER_CHAPTER)
        resolved_max_topics = max(1, min(self.max_topics, len(blocks), max_topics_by_segments))
        resolved_min_topics = max(1, min(self.min_topics, resolved_max_topics))
        resolved_recommended_topics = max(
            resolved_min_topics,
            min(self.recommended_topics, resolved_max_topics),
        )
        min_segments_per_topic = (
            TOPIC_MIN_SEGMENTS_PER_CHAPTER if len(segments) >= TOPIC_MIN_SEGMENTS_PER_CHAPTER else 1
        )

        draft_messages = self.build_topic_draft_prompt(
            blocks,
            len(segments),
            resolved_min_topics,
            resolved_max_topics,
            resolved_recommended_topics,
            min_segments_per_topic,
        )

        try:
            raw_draft = self._run_json_prompt(draft_messages)
            strict_payload = self._normalize_validated_payload(
                raw_draft,
                messages=draft_messages,
                segments=segments,
            )
        except Exception as exc:
            logging.warning(
                "Topic segmentation validation failed for %d segments: %s",
                len(segments),
                exc,
            )
            raise

        plan, titles = _parse_topic_plan_payload(strict_payload)
        topics = _compose_topics(plan, titles, segments)
        return TopicAgentLoopResult(
            payload={"topics": topics},
            debug={
                "iterations": 1,
                "blocks": [_topic_block_to_dict(block) for block in blocks],
                "draft": raw_draft,
                "final": strict_payload,
                "final_source": "draft",
                "issues": [],
            },
        )

    def _run_json_prompt(self, messages: List[Dict[str, str]]) -> str:
        chat_completion_fn = self.chat_completion_fn or llm_utils.chat_completion
        return chat_completion_fn(self.llm_config, messages)

    def _normalize_validated_payload(
        self,
        raw_payload: str,
        *,
        messages: List[Dict[str, str]],
        segments: List["TopicSegment"],
    ) -> dict[str, Any]:
        del messages  # 单次请求合同：topic segmentation 不再隐式 repair/retry。
        return self._validate_payload(
            llm_utils.extract_json(raw_payload),
            segments=segments,
        )

    def _validate_payload(
        self,
        payload: dict[str, Any],
        *,
        segments: List["TopicSegment"],
    ) -> dict[str, Any]:
        strict_payload = _normalize_topic_plan_payload(payload, segments)
        issues = _find_topic_plan_issues(strict_payload, segments)
        if issues:
            raise RuntimeError("; ".join(str(issue.get("message") or "").strip() for issue in issues))
        return strict_payload


def _clean_text(text: str) -> str:
    return SPACE_PATTERN.sub(" ", (text or "").strip())


def _load_kept_segments(srt_path: str, encoding: str) -> List[TopicSegment]:
    with open(srt_path, encoding=encoding) as f:
        subs = list(srt.parse(f.read()))

    segments: List[TopicSegment] = []
    for sub in subs:
        text = parse_decision_and_text(sub.content or "")
        if not text:
            continue
        if text.startswith(REMOVE_TOKEN):
            continue
        if sub.end <= sub.start:
            continue
        segments.append(
            TopicSegment(
                segment_id=int(sub.index),
                start=float(sub.start.total_seconds()),
                end=float(sub.end.total_seconds()),
                text=text,
            )
        )
    segments.sort(key=lambda x: x.start)
    return segments


def _clamp_float(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, int(value)))


def _build_identity_blocks(segments: List[TopicSegment]) -> List[TopicBlock]:
    return [
        TopicBlock(
            block_id=index,
            segment_ids=[segment.segment_id],
            start=segment.start,
            end=segment.end,
            text=_clean_text(segment.text),
        )
        for index, segment in enumerate(segments, start=1)
    ]


def _build_block_spec(segments: List[TopicSegment], recommended_topics: int) -> TopicBlockSpec:
    duration_s = max(0.0, float(segments[-1].end) - float(segments[0].start))
    total_chars = sum(len(_clean_text(segment.text)) for segment in segments)
    target_blocks = max(1, int(round(recommended_topics * TOPIC_BLOCKS_PER_CHAPTER_TARGET)))
    avg_segments_per_block = len(segments) / max(1, target_blocks)
    if len(segments) <= target_blocks or avg_segments_per_block < 3.0:
        return TopicBlockSpec(
            target_seconds=0.0,
            max_seconds=0.0,
            target_chars=0,
            max_chars=0,
            target_segments=1,
            max_segments=1,
            min_tail_seconds=0.0,
            min_tail_chars=0,
            min_tail_segments=1,
            target_blocks=target_blocks,
            pre_chunk_enabled=False,
        )

    target_seconds = _clamp_float(
        duration_s / max(1, target_blocks),
        TOPIC_BLOCK_MIN_SECONDS,
        TOPIC_BLOCK_MAX_TARGET_SECONDS,
    )
    max_seconds = _clamp_float(
        target_seconds * 1.5,
        max(target_seconds + 1.0, TOPIC_BLOCK_MIN_SECONDS),
        TOPIC_BLOCK_MAX_HARD_SECONDS,
    )
    target_chars = _clamp_int(
        int(round(total_chars / max(1, target_blocks))),
        TOPIC_BLOCK_MIN_CHARS,
        TOPIC_BLOCK_MAX_TARGET_CHARS,
    )
    max_chars = _clamp_int(
        int(round(target_chars * 1.4)),
        target_chars + 10,
        TOPIC_BLOCK_MAX_HARD_CHARS,
    )
    target_segments = max(1, int(round(len(segments) / max(1, target_blocks))))
    max_segments = max(target_segments + 1, int(math.ceil(target_segments * 1.5)))
    min_tail_seconds = max(3.0, target_seconds * TOPIC_BLOCK_MIN_TAIL_RATIO)
    min_tail_chars = max(12, int(round(target_chars * TOPIC_BLOCK_MIN_TAIL_RATIO)))
    min_tail_segments = 2 if target_segments >= 2 else 1
    return TopicBlockSpec(
        target_seconds=target_seconds,
        max_seconds=max_seconds,
        target_chars=target_chars,
        max_chars=max_chars,
        target_segments=target_segments,
        max_segments=max_segments,
        min_tail_seconds=min_tail_seconds,
        min_tail_chars=min_tail_chars,
        min_tail_segments=min_tail_segments,
        target_blocks=target_blocks,
        pre_chunk_enabled=True,
    )


def _should_close_block(
    segment_ids: List[int],
    start: float,
    end: float,
    char_count: int,
    spec: TopicBlockSpec,
) -> bool:
    duration = max(0.0, float(end) - float(start))
    segment_count = len(segment_ids)
    if duration >= spec.max_seconds:
        return True
    if char_count >= spec.max_chars:
        return True
    if segment_count >= spec.max_segments:
        return True
    if segment_count < spec.target_segments:
        return False
    return duration >= spec.target_seconds or char_count >= spec.target_chars


def _should_merge_tail_block(block: "TopicBlock", spec: TopicBlockSpec) -> bool:
    duration = max(0.0, float(block.end) - float(block.start))
    char_count = len(_clean_text(block.text))
    return (
        len(block.segment_ids) < spec.min_tail_segments
        or (
            duration < spec.min_tail_seconds
            and char_count < spec.min_tail_chars
        )
    )


def _topic_block_to_dict(block: "TopicBlock") -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "segment_ids": list(block.segment_ids),
        "start": round(block.start, 2),
        "end": round(block.end, 2),
        "text": block.text,
    }


def _build_candidate_blocks(
    segments: List[TopicSegment],
    recommended_topics: int,
) -> List[TopicBlock]:
    spec = _build_block_spec(segments, recommended_topics)
    if not spec.pre_chunk_enabled:
        return _build_identity_blocks(segments)

    blocks: List[TopicBlock] = []
    current_segments: List[TopicSegment] = []
    current_char_count = 0

    def flush_current() -> None:
        nonlocal current_segments, current_char_count
        if not current_segments:
            return
        blocks.append(
            TopicBlock(
                block_id=len(blocks) + 1,
                segment_ids=[segment.segment_id for segment in current_segments],
                start=current_segments[0].start,
                end=current_segments[-1].end,
                text=" ".join(_clean_text(segment.text) for segment in current_segments),
            )
        )
        current_segments = []
        current_char_count = 0

    for segment in segments:
        current_segments.append(segment)
        current_char_count += len(_clean_text(segment.text))
        if _should_close_block(
            [item.segment_id for item in current_segments],
            current_segments[0].start,
            current_segments[-1].end,
            current_char_count,
            spec,
        ):
            flush_current()

    flush_current()

    if len(blocks) >= 2 and _should_merge_tail_block(blocks[-1], spec):
        tail = blocks.pop()
        prev = blocks[-1]
        blocks[-1] = TopicBlock(
            block_id=prev.block_id,
            segment_ids=prev.segment_ids + tail.segment_ids,
            start=prev.start,
            end=tail.end,
            text=f"{prev.text} {tail.text}".strip(),
        )

    return [
        TopicBlock(
            block_id=index,
            segment_ids=list(block.segment_ids),
            start=block.start,
            end=block.end,
            text=block.text,
        )
        for index, block in enumerate(blocks, start=1)
    ]


def _build_segmentation_prompt(
    blocks: List[TopicBlock],
    total_segments: int,
    min_topics: int,
    max_topics: int,
    recommended_topics: int,
    title_max_chars: int,
    min_segments_per_topic: int,
) -> List[Dict[str, str]]:
    recommended_title_chars = _recommended_title_chars(title_max_chars)
    accepted_title_chars = _accepted_title_chars(title_max_chars)
    lines = [
        (
            f"[B{block.block_id:02d}]"
            f"[{block.start:.2f}-{block.end:.2f}]"
            f"[S{block.segment_ids[0]:04d}-S{block.segment_ids[-1]:04d}] "
            f"{block.text}"
        )
        for block in blocks
    ]
    payload = "\n".join(lines)
    system = (
        "你是短视频口播分章器。"
        "输入是已经按时间顺序整理好的候选块。"
        "请把这些 block 合并成最终章节。"
        "你的任务不是给这段内容写摘要，而是给视频章节命名。"
        "请站在视频目录/章节导航的视角思考：这一章放在视频里应该叫什么。"
        "只输出严格 JSON，不要解释。"
        '格式：{"topics":[{"block_range":"1-3","title":"..."}]}。'
        'block_range 虽沿用旧字段名，但这里必须填写连续字幕 segment 编号范围；写成 "起始-结束"，单个字幕写 "4"。'
        f"要求：至少 {min_topics} 章，最多 {max_topics} 章，推荐 {recommended_topics} 章左右；"
        f"基于当前共 {total_segments} 句字幕、每章至少 {min_segments_per_topic} 句，本次最多只能分成 {max_topics} 章；"
        "必须覆盖全部字幕 segment；每章连续、按时间顺序、不能跳号、不能重叠；"
        "每章主题单一，优先在语义自然切换处断开。"
        f"尽量让每章至少包含 {min_segments_per_topic} 句连续字幕（segment）。"
        "title 必须是章节名，不是内容总结句。"
        "title 要像视频上屏章节标题，能让人一眼知道这一章在讲什么。"
        "优先用用户会记住的说法，可以带结论、动作、痛点或亮点。"
        "禁止：章节1、要点2、项目背景、核心功能、使用流程、产品介绍、总结回顾。"
        f"title 尽量控制在 {recommended_title_chars} 字内，一定不要超过 {accepted_title_chars} 字。"
        "title 不要半句话，不要残句，不要以“的/了/和/及/与”结尾。"
    )
    user = f"候选块输入：\n{payload}\n\n请仅输出 topics JSON："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_range_ids(value: Any) -> List[int]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        normalized = int(value)
        return [normalized] if normalized >= 1 else []
    if not isinstance(value, str):
        return []
    match = ID_RANGE_PATTERN.match(value.strip())
    if not match:
        return []
    start_id = int(match.group(1))
    end_raw = match.group(2)
    end_id = int(end_raw) if end_raw is not None else start_id
    if end_id < start_id:
        return []
    return list(range(start_id, end_id + 1))


def _parse_block_range_plan(items: list[Any], *, empty_message: str) -> Tuple[List[List[int]], List[str]]:
    plan: List[List[int]] = []
    titles: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ids = _parse_range_ids(item.get("block_range"))
        if ids:
            plan.append(ids)
            titles.append(_clean_text(str(item.get("title") or "")))
    if not plan:
        raise RuntimeError(empty_message)
    return plan, titles


def _parse_topic_plan_payload(data: dict[str, Any]) -> Tuple[List[List[int]], List[str]]:
    items = data.get("topics")
    if not isinstance(items, list):
        items = data.get("segments")
    if not isinstance(items, list):
        raise RuntimeError("LLM response missing `topics` array.")
    return _parse_block_range_plan(items, empty_message="LLM returned empty segmentation plan.")


def _build_topic_plan_payload(plan: List[List[int]], titles: List[str]) -> dict[str, Any]:
    return {
        "topics": [
            {
                "block_range": str(ids[0]) if ids[0] == ids[-1] else f"{ids[0]}-{ids[-1]}",
                "title": title,
            }
            for ids, title in zip(plan, titles)
        ],
    }


def _parse_segment_plan(text: str) -> List[List[int]]:
    plan, _ = _parse_topic_plan_payload(llm_utils.extract_json(text))
    return plan


def _is_strictly_increasing(ids: List[int]) -> bool:
    if not ids:
        return False
    for index in range(1, len(ids)):
        if ids[index] <= ids[index - 1]:
            return False
    return True


def _normalize_id_plan(plan: List[List[int]], ordered_ids: List[int], label: str) -> List[List[int]]:
    cursor = 0
    normalized: List[List[int]] = []

    for index, ids in enumerate(plan, start=1):
        ids = [int(value) for value in ids]
        if ids != sorted(ids) or not _is_strictly_increasing(ids):
            raise RuntimeError(f"{label} plan {index} must be strictly increasing.")
        if cursor >= len(ordered_ids):
            raise RuntimeError(f"{label} plan exceeds input range.")
        expected = ordered_ids[cursor : cursor + len(ids)]
        if ids != expected:
            raise RuntimeError(
                f"{label} plan {index} not aligned with timeline (expected {expected}, got {ids})."
            )
        normalized.append(ids)
        cursor += len(ids)

    if cursor != len(ordered_ids):
        raise RuntimeError(f"{label} plan does not fully cover input.")
    return normalized


def _normalize_segment_plan(
    plan: List[List[int]], segments: List[TopicSegment]
) -> List[List[int]]:
    return _normalize_id_plan(plan, [segment.segment_id for segment in segments], "Segment")


def _normalize_topic_plan_payload(
    payload: dict[str, Any], segments: List[TopicSegment]
) -> dict[str, Any]:
    plan, titles = _parse_topic_plan_payload(payload)
    normalized_segments = _normalize_segment_plan(plan, segments)
    return _build_topic_plan_payload(normalized_segments, titles)


def _find_topic_plan_issues(
    payload: dict[str, Any],
    segments: List[TopicSegment],
) -> List[dict[str, Any]]:
    try:
        strict_payload = _normalize_topic_plan_payload(payload, segments)
        _, titles = _parse_topic_plan_payload(strict_payload)
    except Exception as exc:
        return [{"topic_index": 0, "message": f"topics JSON 无法解析: {exc}"}]

    issues: List[dict[str, Any]] = []
    for index, title in enumerate(titles, start=1):
        value = _clean_text(title)
        if not value:
            issues.append({"topic_index": index, "message": "标题为空。"})
    return issues


def _is_topic_plan_valid(
    payload: dict[str, Any],
    segments: List[TopicSegment],
) -> bool:
    return not _find_topic_plan_issues(payload, segments)


def _compose_topics(
    plan: List[List[int]],
    titles: List[str],
    segments: List[TopicSegment],
) -> List[Dict[str, Any]]:
    segment_map = {segment.segment_id: segment for segment in segments}
    topics: List[Dict[str, Any]] = []
    for index, ids in enumerate(plan, start=1):
        chosen = [segment_map[value] for value in ids if value in segment_map]
        if not chosen:
            continue
        title = _clean_text(titles[index - 1] or f"章节{index}") or f"章节{index}"
        topics.append(
            {
                "title": title,
                "block_range": str(ids[0]) if ids[0] == ids[-1] else f"{ids[0]}-{ids[-1]}",
                "start": round(chosen[0].start, 2),
                "end": round(chosen[-1].end, 2),
            }
        )
    return topics


def _default_output_path(srt_path: str) -> str:
    srt_abs = os.path.abspath(srt_path)
    directory = os.path.dirname(srt_abs)
    stem = os.path.splitext(os.path.basename(srt_abs))[0]
    if stem.endswith(".optimized"):
        stem = stem[: -len(".optimized")]
    return os.path.join(directory, f"{stem}.topics.json")


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TopicSegmenter:
    def __init__(
        self,
        args_or_input,
        options: PipelineOptions | None = None,
        *,
        output_path: str | Path | None = None,
    ):
        self.options = options
        self.args = args_or_input if options is None else None
        if options is None:
            self.inputs = [str(path) for path in getattr(args_or_input, "inputs", [])]
            self.encoding = str(getattr(args_or_input, "encoding", "utf-8"))
            self.output_path = getattr(args_or_input, "topic_output", None)
            self.max_topics = max(
                1, min(TOPIC_MAX_TOPICS_HARD_CAP, int(getattr(args_or_input, "topic_max_topics", 5)))
            )
            self.title_max_chars = int(
                getattr(
                    args_or_input,
                    "topic_title_max_chars",
                    TOPIC_TITLE_MAX_CHARS_DEFAULT,
                )
            )
            self.strict = bool(getattr(args_or_input, "topic_strict", False))
            llm_base_url = getattr(args_or_input, "llm_base_url", None)
            llm_model = getattr(args_or_input, "llm_model", None)
            llm_api_key = getattr(args_or_input, "llm_api_key", None)
            llm_timeout = getattr(args_or_input, "llm_timeout", 60)
            llm_temperature = getattr(args_or_input, "llm_temperature", 0.2)
            llm_max_tokens = getattr(args_or_input, "llm_max_tokens", None)
        else:
            self.inputs = [str(Path(args_or_input))]
            self.encoding = options.encoding
            self.output_path = str(output_path) if output_path is not None else options.topic_output
            self.max_topics = max(1, min(TOPIC_MAX_TOPICS_HARD_CAP, int(options.topic_max_topics)))
            self.title_max_chars = int(options.topic_title_max_chars)
            self.strict = bool(options.topic_strict)
            llm_base_url = options.llm_base_url
            llm_model = options.llm_model or options.topic_llm_model
            llm_api_key = options.llm_api_key
            llm_timeout = options.llm_timeout
            llm_temperature = options.llm_temperature
            llm_max_tokens = options.llm_max_tokens
        self.max_topics = max(
            1, min(TOPIC_MAX_TOPICS_HARD_CAP, int(self.max_topics))
        )
        if self.title_max_chars < 1:
            raise RuntimeError("--topic-title-max-chars must be >= 1.")
        self.llm_config = llm_utils.build_llm_config(
            base_url=llm_base_url,
            model=llm_model,
            api_key=llm_api_key,
            timeout=llm_timeout,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
            enable_thinking=False,
        )
        if not self.llm_config.get("base_url") or not self.llm_config.get("model"):
            raise RuntimeError(
                "LLM config missing. Set --llm-base-url and --llm-model for topic segmentation."
            )

    def run(self):
        output_path = self.output_path
        srt_inputs = [path for path in self.inputs if path.lower().endswith(".srt")]
        if not srt_inputs:
            raise RuntimeError("Topic segmentation requires at least one .srt input.")
        if output_path and len(srt_inputs) > 1:
            raise RuntimeError("--topic-output can only be used with a single .srt input.")

        for srt_path in srt_inputs:
            target = output_path if output_path else None
            self.run_for_srt(srt_path, output_path=target)

    def run_for_srt(self, srt_path: str, output_path: Optional[str] = None) -> str:
        segments = _load_kept_segments(srt_path, self.encoding)
        if not segments:
            raise RuntimeError(f"No kept subtitles found for topic segmentation: {srt_path}")
        duration_s = max(0.0, float(segments[-1].end) - float(segments[0].start))
        min_topics, recommended_topics, desired_max_topics = _topic_count_range(duration_s)
        max_topics = max(self.max_topics, desired_max_topics)

        topic_loop = PiAgentTopicLoop(
            self.llm_config,
            min_topics=min_topics,
            max_topics=max_topics,
            recommended_topics=recommended_topics,
            title_max_chars=self.title_max_chars,
            strict=self.strict,
        )
        result = topic_loop.run(segments)
        output = output_path or _default_output_path(srt_path)
        _write_json(output, result.payload)
        logging.info("Saved topic segments to %s", output)
        return output
