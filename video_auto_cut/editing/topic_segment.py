import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import srt

from . import llm_client as llm_utils


DECISION_HEADER_PATTERN = re.compile(r"^\[(KEEP|REMOVE)\b[^\]]*\]\s*$", re.IGNORECASE)
REMOVE_TOKEN = "<<REMOVE>>"
SPACE_PATTERN = re.compile(r"\s+")
TOPIC_SUMMARY_MAX_CHARS_DEFAULT = 6
TOPIC_TITLE_MAX_CHARS_DEFAULT = 6
CUE_RULES = [
    ("FIRST", re.compile(r"(第一|首先|先说|先讲|第一点|第1点)")),
    ("SECOND", re.compile(r"(第二|其次|然后|接着|再者|另一方面|另外)")),
    ("THIRD", re.compile(r"(第三|第三点|第3点)")),
    ("FOURTH", re.compile(r"(第四|第四点|第4点)")),
    ("LAST", re.compile(r"(最后|最终|总之|总结|结尾|最后一点)")),
]


@dataclass
class TopicSegment:
    segment_id: int
    start: float
    end: float
    text: str
    cue: Optional[str] = None


def _strip_code_fence(text: str) -> str:
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    if len(parts) >= 3:
        return parts[1].strip()
    return text.strip()


def _clean_text(text: str) -> str:
    return SPACE_PATTERN.sub(" ", (text or "").strip())


def _detect_cue(text: str) -> Optional[str]:
    value = _clean_text(text)
    for cue, pattern in CUE_RULES:
        if pattern.search(value):
            return cue
    return None


def _parse_decision_and_text(content: str) -> Tuple[Optional[str], str]:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        return None, ""
    first = lines[0]
    match = DECISION_HEADER_PATTERN.match(first)
    if not match:
        return None, "\n".join(lines).strip()
    decision = match.group(1).upper()
    text = "\n".join(lines[1:]).strip()
    return decision, text


def _load_kept_segments(srt_path: str, encoding: str) -> List[TopicSegment]:
    with open(srt_path, encoding=encoding) as f:
        subs = list(srt.parse(f.read()))

    segments: List[TopicSegment] = []
    for sub in subs:
        decision, text = _parse_decision_and_text(sub.content or "")
        if decision == "REMOVE":
            continue
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
                cue=_detect_cue(text),
            )
        )
    segments.sort(key=lambda x: x.start)
    return segments


def _build_segmentation_prompt(
    segments: List[TopicSegment], max_topics: int, title_max_chars: int
) -> List[Dict[str, str]]:
    max_topics = max(2, int(max_topics))
    min_topics = 1 if len(segments) < 4 else 2
    normal_title_max_chars = max(1, int(title_max_chars))
    short_title_max_chars = min(4, normal_title_max_chars)
    lines: List[str] = []
    for seg in segments:
        cue = seg.cue or "NONE"
        lines.append(
            f"[S{seg.segment_id:04d}][{seg.start:.2f}-{seg.end:.2f}][CUE={cue}] {seg.text}"
        )
    payload = "\n".join(lines)

    system = (
        "你是短视频口播分章编辑，先做分段，不做总结。"
        "背景：口播通常是总分总结构：开头intro，中间按分点展开，结尾收尾。"
        "显式线索（第一/首先/第二/第三/第四/最后/总结）应优先作为分段边界。"
        "输出严格 JSON，不要 markdown，不要解释。"
        '格式：{"segments":[{"segment_ids":[1,2,3],"title":"章节标题"}]}。'
        "要求："
        "1) 覆盖全部 segment，不遗漏；"
        "2) 每段连续，不重叠，不跳号；"
        "3) 按时间顺序；"
        "4) 分段数控制在 "
        f"{min_topics}"
        " 到 "
        f"{max_topics}"
        f"；5) title 要概括该段核心信息：常规不超过 {normal_title_max_chars} 个字；"
        f"若该段只包含 1~2 条字幕句子，title 必须不超过 {short_title_max_chars} 个字。"
        "6) segment_ids 必须直接复用输入中的 S 编号。"
    )
    user = f"字幕输入：\n{payload}\n\n请仅输出分段 JSON："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_segment_ids(item: Dict[str, Any]) -> List[int]:
    ids_raw = item.get("segment_ids")
    if isinstance(ids_raw, list):
        ids: List[int] = []
        for value in ids_raw:
            try:
                ids.append(int(value))
            except Exception:
                continue
        if ids:
            return ids

    start_raw = item.get("start_segment_id")
    end_raw = item.get("end_segment_id")
    if start_raw is None or end_raw is None:
        return []
    try:
        start_id = int(start_raw)
        end_id = int(end_raw)
    except Exception:
        return []
    if end_id < start_id:
        return []
    return list(range(start_id, end_id + 1))


def _parse_segment_plan(text: str) -> Tuple[List[List[int]], Dict[int, str]]:
    raw = _strip_code_fence(text)
    data = llm_utils.extract_json(raw)
    items = data.get("segments")
    if not isinstance(items, list):
        raise RuntimeError("LLM response missing `segments` array.")

    plan: List[List[int]] = []
    titles: Dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ids = _parse_segment_ids(item)
        if ids:
            plan.append(ids)
            idx = len(plan)
            title = _clean_text(str(item.get("title") or ""))
            if title:
                titles[idx] = title
    if not plan:
        raise RuntimeError("LLM returned empty segmentation plan.")
    return plan, titles


def _is_strictly_increasing(ids: List[int]) -> bool:
    if not ids:
        return False
    for i in range(1, len(ids)):
        if ids[i] <= ids[i - 1]:
            return False
    return True


def _normalize_segment_plan(
    plan: List[List[int]], segments: List[TopicSegment]
) -> List[List[int]]:
    ordered_ids = [seg.segment_id for seg in segments]
    cursor = 0
    normalized: List[List[int]] = []

    for idx, ids in enumerate(plan, start=1):
        ids = [int(v) for v in ids]
        if ids != sorted(ids) or not _is_strictly_increasing(ids):
            raise RuntimeError(f"Segment plan {idx} must be strictly increasing.")
        if cursor >= len(ordered_ids):
            raise RuntimeError("Segment plan exceeds subtitle range.")

        expected = ordered_ids[cursor : cursor + len(ids)]
        if ids != expected:
            raise RuntimeError(
                f"Segment plan {idx} not aligned with timeline (expected {expected}, got {ids})."
            )
        normalized.append(ids)
        cursor += len(ids)

    if cursor != len(ordered_ids):
        raise RuntimeError("Segment plan does not fully cover subtitles.")
    return normalized


def _build_cue_fallback_plan(segments: List[TopicSegment], max_topics: int) -> List[List[int]]:
    if not segments:
        return []

    boundaries = [0]
    for idx, seg in enumerate(segments[1:], start=1):
        if seg.cue is not None:
            boundaries.append(idx)
    boundaries = sorted(set(boundaries))
    boundaries.append(len(segments))

    ranges: List[List[int]] = []
    for i in range(len(boundaries) - 1):
        chosen = segments[boundaries[i] : boundaries[i + 1]]
        ids = [seg.segment_id for seg in chosen]
        if ids:
            ranges.append(ids)

    while len(ranges) > max_topics:
        tail = ranges.pop()
        ranges[-1].extend(tail)
    return ranges


def _topic_role(index: int, total: int) -> str:
    if total == 1:
        return "BODY"
    if index == 1:
        return "INTRO"
    if index == total:
        return "OUTRO"
    return "BODY"


def _build_summary_prompt(
    plan: List[List[int]],
    segments: List[TopicSegment],
    summary_max_chars: int,
    title_max_chars: int,
) -> List[Dict[str, str]]:
    normal_title_max_chars = max(1, int(title_max_chars))
    short_title_max_chars = min(4, normal_title_max_chars)
    id_to_segment = {seg.segment_id: seg for seg in segments}
    lines: List[str] = []
    for idx, ids in enumerate(plan, start=1):
        role = _topic_role(idx, len(plan))
        chosen = [id_to_segment[x] for x in ids if x in id_to_segment]
        text = " ".join(_clean_text(seg.text) for seg in chosen)
        start_id = ids[0]
        end_id = ids[-1]
        lines.append(
            f"[T{idx:02d}][ROLE={role}][N={len(ids)}][S{start_id:04d}-S{end_id:04d}] {text}"
        )
    payload = "\n".join(lines)

    system = (
        "你是短视频口播文案编辑。现在仅做标题和摘要，不改分段。"
        "输入里每一行是一段已确定的章节。"
        "请根据每段文本生成高信息标题与摘要，便于视频上屏展示。"
        "要求："
        "1) 不要空话、套话；"
        "2) 摘要要具体到该段核心信息；"
        f"3) 标题精炼：常规不超过 {normal_title_max_chars} 字；若该段 N=1 或 N=2，标题必须不超过 {short_title_max_chars} 字；"
        f"4) 摘要必须不超过 {max(1, summary_max_chars)} 字；"
        "5) 保持章节顺序和数量一致。"
        "输出严格 JSON，不要 markdown，不要解释。"
        '格式：{"topics":[{"topic_index":1,"title":"...","summary":"..."}]}'
    )
    user = f"已分段文本：\n{payload}\n\n请仅输出标题摘要 JSON："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_summary_plan(text: str, topic_count: int) -> List[Tuple[str, str]]:
    raw = _strip_code_fence(text)
    data = llm_utils.extract_json(raw)
    items = data.get("topics")
    if not isinstance(items, list):
        raise RuntimeError("LLM response missing `topics` array.")

    bucket: Dict[int, Tuple[str, str]] = {}
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        raw_index = item.get("topic_index", idx)
        try:
            topic_index = int(raw_index)
        except Exception:
            topic_index = idx
        if topic_index < 1 or topic_index > topic_count:
            continue
        title = _clean_text(str(item.get("title") or "")) or f"章节{topic_index}"
        summary = _clean_text(str(item.get("summary") or ""))
        bucket[topic_index] = (title, summary)

    result: List[Tuple[str, str]] = []
    for index in range(1, topic_count + 1):
        title, summary = bucket.get(index, (f"章节{index}", ""))
        result.append((title, summary))
    return result


def _fallback_title_summary(
    ids: List[int], segments: List[TopicSegment], index: int, total: int
) -> Tuple[str, str]:
    id_to_segment = {seg.segment_id: seg for seg in segments}
    chosen = [id_to_segment[x] for x in ids if x in id_to_segment]
    base = _clean_text(chosen[0].text) if chosen else "内容"
    if total == 1:
        title = "内容概览"
    elif index == 1:
        title = "开场"
    elif index == total:
        title = "收尾"
    else:
        title = f"要点{index}"
    return title, base


def _fallback_title_only(
    ids: List[int], segments: List[TopicSegment], index: int, total: int, title_max_chars: int
) -> str:
    id_to_segment = {seg.segment_id: seg for seg in segments}
    chosen = [id_to_segment[x] for x in ids if x in id_to_segment]
    if chosen:
        base = _clean_text(chosen[0].text)
        base = re.sub(r"^[\s\-—,，。！？!?；;：:]+", "", base)
        clause = re.split(r"[，。！？!?；;：:]", base)[0].strip()
        if clause and len(clause) <= title_max_chars:
            return clause
    if total == 1:
        return "总览" if title_max_chars >= 2 else "总"
    if index == 1:
        return "开场"
    if index == total:
        return "结尾"
    return f"要点{index}"


def _cap_summary(summary: str, max_chars: int) -> str:
    value = _clean_text(summary)
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _compose_topics(
    plan: List[List[int]],
    title_summary_pairs: List[Tuple[str, str]],
    segments: List[TopicSegment],
    summary_max_chars: int,
    title_max_chars: int,
) -> List[Dict[str, Any]]:
    id_to_segment = {seg.segment_id: seg for seg in segments}
    topics: List[Dict[str, Any]] = []
    for idx, ids in enumerate(plan, start=1):
        chosen = [id_to_segment[x] for x in ids if x in id_to_segment]
        if not chosen:
            continue
        raw_title, raw_summary = title_summary_pairs[idx - 1]
        if not raw_summary:
            _, summary = _fallback_title_summary(ids, segments, idx, len(plan))
            raw_summary = summary
        title = _clean_text(raw_title or f"章节{idx}") or f"章节{idx}"
        summary = _clean_text(raw_summary)
        # No-summary mode uses summary==title.
        if not summary or summary == _clean_text(raw_title):
            summary = title
        if summary != title:
            summary = _cap_summary(summary, summary_max_chars)
        else:
            summary = _clean_text(summary)
        topics.append(
            {
                "title": title or f"章节{idx}",
                "summary": summary,
                "segment_ids": ids,
                "start": round(chosen[0].start, 2),
                "end": round(chosen[-1].end, 2),
                "start_segment_id": ids[0],
                "end_segment_id": ids[-1],
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
    def __init__(self, args):
        self.args = args
        self.max_topics = int(getattr(args, "topic_max_topics", 8))
        self.generate_summary = bool(getattr(args, "topic_generate_summary", True))
        self.summary_max_chars = int(
            getattr(
                args,
                "topic_summary_max_chars",
                TOPIC_SUMMARY_MAX_CHARS_DEFAULT,
            )
        )
        if self.summary_max_chars < 1:
            raise RuntimeError("--topic-summary-max-chars must be >= 1.")
        self.title_max_chars = int(
            getattr(
                args,
                "topic_title_max_chars",
                TOPIC_TITLE_MAX_CHARS_DEFAULT,
            )
        )
        if self.title_max_chars < 1:
            raise RuntimeError("--topic-title-max-chars must be >= 1.")
        self.strict = bool(getattr(args, "topic_strict", False))
        self.llm_config = llm_utils.build_llm_config(
            base_url=getattr(args, "llm_base_url", None),
            model=getattr(args, "llm_model", None),
            api_key=getattr(args, "llm_api_key", None),
            timeout=getattr(args, "llm_timeout", 60),
            temperature=getattr(args, "llm_temperature", 0.2),
            max_tokens=getattr(args, "llm_max_tokens", 1024),
        )
        if not self.llm_config.get("base_url") or not self.llm_config.get("model"):
            raise RuntimeError(
                "LLM config missing. Set --llm-base-url and --llm-model for topic segmentation."
            )

    def run(self):
        output_path = getattr(self.args, "topic_output", None)
        srt_inputs = [path for path in self.args.inputs if path.lower().endswith(".srt")]
        if not srt_inputs:
            raise RuntimeError("Topic segmentation requires at least one .srt input.")
        if output_path and len(srt_inputs) > 1:
            raise RuntimeError("--topic-output can only be used with a single .srt input.")

        for srt_path in srt_inputs:
            target = output_path if output_path else None
            self.run_for_srt(srt_path, output_path=target)

    def run_for_srt(self, srt_path: str, output_path: Optional[str] = None) -> str:
        segments = _load_kept_segments(srt_path, getattr(self.args, "encoding", "utf-8"))
        if not segments:
            raise RuntimeError(f"No kept subtitles found for topic segmentation: {srt_path}")

        seg_prompt = _build_segmentation_prompt(segments, self.max_topics, self.title_max_chars)
        seg_text = llm_utils.chat_completion(self.llm_config, seg_prompt)
        seg_titles: Dict[int, str] = {}
        try:
            plan, seg_titles = _parse_segment_plan(seg_text)
            plan = _normalize_segment_plan(plan, segments)
        except Exception as exc:
            if self.strict:
                raise
            logging.warning(f"Segmentation parsing failed, fallback to cue plan: {exc}")
            plan = _build_cue_fallback_plan(segments, self.max_topics)

        if self.generate_summary:
            sum_prompt = _build_summary_prompt(
                plan, segments, self.summary_max_chars, self.title_max_chars
            )
            sum_text = llm_utils.chat_completion(self.llm_config, sum_prompt)
            try:
                pairs = _parse_summary_plan(sum_text, topic_count=len(plan))
            except Exception as exc:
                if self.strict:
                    raise
                logging.warning(f"Summary parsing failed, fallback to text lead: {exc}")
                pairs = []
                for idx, ids in enumerate(plan, start=1):
                    pairs.append(_fallback_title_summary(ids, segments, idx, len(plan)))
            summary_max_chars = self.summary_max_chars
        else:
            pairs = []
            for idx, ids in enumerate(plan, start=1):
                title = seg_titles.get(idx) or _fallback_title_only(
                    ids, segments, idx, len(plan), self.title_max_chars
                )
                pairs.append((title, title))
            summary_max_chars = max(32, self.summary_max_chars)

        topics = _compose_topics(
            plan,
            pairs,
            segments,
            summary_max_chars=summary_max_chars,
            title_max_chars=self.title_max_chars,
        )
        output = output_path or _default_output_path(srt_path)
        _write_json(output, {"topics": topics})
        logging.info(f"Saved topic segments to {output}")
        return output
