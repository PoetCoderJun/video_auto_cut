import datetime
import json
import logging
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import srt

from . import llm_client as llm_utils
from .topic_segment import TopicSegmenter


REMOVE_TOKEN = "<<REMOVE>>"
TAG_PATTERN = re.compile(r"^\[L(\d{1,6})\]\s*(.*)$")
NO_SPEECH_PATTERN = re.compile(
    r"^\s*<\s*(?:no|low)[\s_-]*speech\s*>\s*$",
    re.IGNORECASE,
)
TIME_PREFIX_PATTERN = re.compile(r"^\[\d{1,3}:\d{2}\]\s*")
JOIN_PUNCTUATION = set("，、；：,.!?！？。")
TRAILING_LINE_PUNCTUATION = "，。、；：!！"
AUTO_EDIT_CHUNK_LINES = 30
AUTO_EDIT_CHUNK_OVERLAP_LINES = 4
MERGE_SHORT_LINES_THRESHOLD = 20  # 字数阈值：低于此值的短句将尝试合并


@dataclass
class AutoEditConfig:
    merge_gap_s: float = 0.5
    pad_head_s: float = 0.0
    pad_tail_s: float = 0.0


def _segments_to_tagged_text(segments: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        text = (seg.get("text") or "").strip()
        start_s = max(0.0, float(seg.get("start") or 0.0))
        minutes = int(start_s // 60)
        seconds = int(start_s % 60)
        stamp = f"{minutes:02d}:{seconds:02d}"
        lines.append(f"[L{idx:04d}] [{stamp}] {text}")
    return "\n".join(lines)


def _build_llm_remove_prompt(tagged_text: str) -> List[Dict[str, str]]:
    system = (
        "你是口播删改助手。输入是逐句ASR。"
        "背景：说话人录口播时会一边组织语言一边说，所以经常先说错，再连续补救，最后重说一遍。"
        "只保留最后那句真正定稿的话。"
        "优先删除：试探表达、回头修正、半句、重复句、前面那版错误表达。"
        "只做删除，不改写。按时间从后往前判断；同义只留最后一句。"
        f"删除输出 {REMOVE_TOKEN}，保留行原样回填。保留标签，行数一致，不要解释。"
    )
    user = f"原文：\n{tagged_text}\n\n请输出第一步删减结果："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_llm_optimize_prompt(tagged_text: str) -> List[Dict[str, str]]:
    system = (
        "你是口播润色助手。把每一行整理成最终口播会说出来的版本。"
        "修正明显ASR错字，去掉口头语和拖沓重复，但尽量保留原句关键信息和原有说法，不要过度改写。"
        "表达要直接、自然、完整。不要跨行。"
        "行内停顿优先用逗号；除问句外行尾不要标点。"
        f"{REMOVE_TOKEN} 行原样输出。保留标签，行数一致，不要解释。"
    )
    user = f"第一步结果：\n{tagged_text}\n\n请输出第二步优化结果："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _strip_code_fence(text: str) -> str:
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    if len(parts) >= 3:
        return parts[1].strip()
    return text.strip()


def _parse_tagged_output(
    text: str, segments: List[Dict[str, Any]]
) -> Tuple[Dict[int, str], List[int], List[int], str]:
    cleaned = _strip_code_fence(text)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    values: Dict[int, str] = {}
    seen: set = set()
    duplicates: List[int] = []

    for line in lines:
        match = TAG_PATTERN.match(line)
        if not match:
            continue
        idx = int(match.group(1))
        content = (match.group(2) or "").strip()
        if idx in seen:
            duplicates.append(idx)
        values[idx] = content
        seen.add(idx)

    missing: List[int] = []
    for i in range(1, len(segments) + 1):
        if i not in seen:
            missing.append(i)

    return values, missing, duplicates, cleaned


def _is_remove_line(content: str) -> bool:
    value = (content or "").strip()
    value = TIME_PREFIX_PATTERN.sub("", value)
    if not value:
        return True
    if value == REMOVE_TOKEN:
        return True
    if value.startswith(REMOVE_TOKEN):
        return True
    return False


def _is_no_speech_text(content: str) -> bool:
    value = (content or "").strip()
    if not value:
        return True
    return bool(NO_SPEECH_PATTERN.match(value))


def _normalize_line_text(text: str) -> str:
    value = (text or "").strip()
    while value and value[-1] in TRAILING_LINE_PUNCTUATION:
        value = value[:-1].rstrip()
    return value


def _smart_join_text(left: str, right: str) -> str:
    left_text = _normalize_line_text(left)
    right_text = _normalize_line_text(right)
    if not left_text:
        return right_text
    if not right_text:
        return left_text
    if left_text.endswith(("？", "?")):
        if right_text[0] in JOIN_PUNCTUATION:
            return left_text + right_text[1:].lstrip()
        return left_text + right_text
    return left_text + "，" + right_text


def _merge_short_lines(
    segments: List[Dict[str, Any]],
    remove_flags: List[bool],
    threshold: int = MERGE_SHORT_LINES_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    合并短句字幕：将字数低于阈值的行与相邻行合并，返回合并后的新 segments（行数减少）。
    
    规则：
    1. 从左到右遍历保留的行
    2. 如果当前行字数 < threshold，持续与后续行合并，直到：
       - 合并后的字数 >= threshold，或
       - 没有更多行可合并
    3. 如果当前行字数 >= threshold，直接保留（不向后合并）
    4. 合并时：文字用逗号连接，时间戳取合并范围的最小start和最大end
    5. 被合并的行直接从结果中移除
    
    返回合并后的 segments 列表（行数可能少于输入）
    """
    n = len(segments)
    merged_segments: List[Dict[str, Any]] = []
    
    i = 0
    while i < n:
        if remove_flags[i]:
            # 已删除的行，跳过（不加入结果）
            i += 1
            continue
        
        current_seg = dict(segments[i])
        current_text = (current_seg.get("text") or "").strip()
        merged_start = float(current_seg.get("start") or 0.0)
        merged_end = float(current_seg.get("end") or 0.0)
        
        # 如果当前行字数已达到阈值，直接保留（不向后合并）
        if len(current_text) >= threshold:
            merged_segments.append({
                "id": current_seg.get("id"),
                "start": merged_start,
                "end": merged_end,
                "duration": max(0.0, merged_end - merged_start),
                "text": current_text,
            })
            i += 1
            continue
        
        # 当前行是短句，持续合并后续行
        j = i + 1
        while j < n:
            # 跳过已删除的行
            if remove_flags[j]:
                j += 1
                continue
            
            next_seg = segments[j]
            next_text = (next_seg.get("text") or "").strip()
            
            # 合并下一行（无论长短）
            current_text = current_text + "，" + next_text
            merged_start = min(merged_start, float(next_seg.get("start") or 0.0))
            merged_end = max(merged_end, float(next_seg.get("end") or 0.0))
            j += 1
            
            # 如果达到阈值，停止合并
            if len(current_text) >= threshold:
                break
        
        merged_segments.append({
            "id": current_seg.get("id"),
            "start": merged_start,
            "end": merged_end,
            "duration": max(0.0, merged_end - merged_start),
            "text": current_text,
        })
        
        # 跳到已处理范围的下一行
        i = j
    
    return merged_segments


def _segments_to_edl(
    segments: List[Dict[str, Any]], cfg: AutoEditConfig, total_length: Optional[float]
) -> List[Dict[str, float]]:
    edl: List[Dict[str, float]] = []
    for seg in segments:
        start = float(seg.get("start") or 0.0) - cfg.pad_head_s
        end = float(seg.get("end") or 0.0) + cfg.pad_tail_s
        start = max(0.0, start)
        if total_length is not None:
            end = min(total_length, end)
        if end <= start:
            continue
        if not edl:
            edl.append({"start": start, "end": end})
            continue
        if start - edl[-1]["end"] <= cfg.merge_gap_s:
            edl[-1]["end"] = max(edl[-1]["end"], end)
        else:
            edl.append({"start": start, "end": end})
    return edl


def _load_segments(input_path: str, encoding: str) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".srt":
        with open(input_path, encoding=encoding) as f:
            subs = list(srt.parse(f.read()))
        segments: List[Dict[str, Any]] = []
        total_length = None
        for sub in subs:
            start = sub.start.total_seconds()
            end = sub.end.total_seconds()
            segments.append(
                {
                    "id": int(sub.index),
                    "start": start,
                    "end": end,
                    "duration": max(0.0, end - start),
                    "text": sub.content.strip(),
                }
            )
            total_length = max(total_length or 0.0, end)
        return segments, total_length

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        segments = data.get("segments") or []
        total_length = data.get("total_length")
    else:
        segments = data
        total_length = None

    results: List[Dict[str, Any]] = []
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        results.append(
            {
                "id": int(seg.get("id") or (idx + 1)),
                "start": start,
                "end": end,
                "duration": max(0.0, end - start),
                "text": (seg.get("text") or "").strip(),
            }
        )
    return results, total_length


def _write_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_optimized_srt(path: str, subs: List[srt.Subtitle], encoding: str):
    with open(path, "wb") as f:
        f.write(srt.compose(subs, reindex=False).encode(encoding, "replace"))


class AutoEdit:
    def __init__(self, args):
        self.args = args
        self.cfg = AutoEditConfig(
            merge_gap_s=float(getattr(args, "auto_edit_merge_gap", 0.5)),
            pad_head_s=float(getattr(args, "auto_edit_pad_head", 0.0)),
            pad_tail_s=float(getattr(args, "auto_edit_pad_tail", 0.0)),
        )

        if not bool(getattr(args, "auto_edit_llm", False)):
            raise RuntimeError("Auto-edit requires --auto-edit-llm.")

        self.llm_config = llm_utils.build_llm_config(
            base_url=self.args.llm_base_url,
            model=self.args.llm_model,
            api_key=self.args.llm_api_key,
            timeout=self.args.llm_timeout,
            temperature=0.0,
            max_tokens=self.args.llm_max_tokens,
            enable_thinking=False,
        )
        if not self.llm_config.get("base_url") or not self.llm_config.get("model"):
            raise RuntimeError(
                "LLM config missing. Set --llm-base-url and --llm-model to use auto-edit LLM."
            )

        self.topic_segmenter = None
        if bool(getattr(self.args, "auto_edit_topics", False)):
            self.topic_segmenter = TopicSegmenter(self.args)

    def run(self):
        for input_path in self.args.inputs:
            segments, total_length = _load_segments(input_path, self.args.encoding)
            if not segments:
                logging.warning(f"No segments found in {input_path}")
                continue

            base, _ = os.path.splitext(input_path)
            optimized_srt = base + ".optimized.srt"
            cache_dir = Path.cwd() / ".cache" / "auto_edit"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_base = cache_dir / os.path.basename(base)
            edl_json = str(cache_base) + ".edl.json"
            debug_json = str(cache_base) + ".debug.json"

            if _maybe_skip(optimized_srt, self.args.force):
                continue

            result = self._auto_edit_segments(segments, total_length)
            _write_optimized_srt(optimized_srt, result["optimized_subs"], self.args.encoding)
            logging.info(f"Saved optimized SRT to {optimized_srt}")
            _write_json(edl_json, result["edl"])
            _write_json(debug_json, result["debug"])

            if self.topic_segmenter:
                topic_output = self._resolve_topic_output(optimized_srt)
                try:
                    self.topic_segmenter.run_for_srt(
                        optimized_srt, output_path=topic_output
                    )
                except Exception as exc:
                    if bool(getattr(self.args, "topic_strict", False)):
                        raise
                    logging.warning(f"Topic segmentation skipped due to error: {exc}")

    def _auto_edit_segments(
        self, segments: List[Dict[str, Any]], total_length: Optional[float]
    ) -> Dict[str, Any]:
        # 先执行删除+润色（可能分 chunk）
        if len(segments) <= AUTO_EDIT_CHUNK_LINES:
            chunk_result = self._auto_edit_segment_chunk(segments)
            if not chunk_result["kept_segments"]:
                raise RuntimeError("All segments removed. Check LLM output.")
            # Step 3: 合并短句（在删除+润色完成后）
            # 从 optimized_subs 中提取 segment 信息（与 subs 一一对应）
            segment_infos = [
                {"start": seg["start"], "end": seg["end"]}
                for seg in segments
            ]
            merged_subs, merged_segments = self._merge_short_lines_in_subs(
                chunk_result["optimized_subs"], 
                segment_infos
            )
            edl = _segments_to_edl(merged_segments, self.cfg, total_length)
            return {
                "optimized_subs": merged_subs,
                "edl": edl,
                "debug": chunk_result["debug"],
            }

        logging.info(
            "[auto_edit] segment count=%d exceeds chunk limit=%d, processing in chunks (overlap=%d)",
            len(segments),
            AUTO_EDIT_CHUNK_LINES,
            AUTO_EDIT_CHUNK_OVERLAP_LINES,
        )
        optimized_subs_all: List[srt.Subtitle] = []
        kept_segments_all: List[Dict[str, Any]] = []
        chunk_debug: List[Dict[str, Any]] = []

        for chunk_index, start in enumerate(range(0, len(segments), AUTO_EDIT_CHUNK_LINES), start=1):
            end = min(start + AUTO_EDIT_CHUNK_LINES, len(segments))
            left_overlap = min(AUTO_EDIT_CHUNK_OVERLAP_LINES, start)
            right_overlap = min(AUTO_EDIT_CHUNK_OVERLAP_LINES, len(segments) - end)
            context_start = start - left_overlap
            context_end = end + right_overlap
            seg_chunk = segments[context_start:context_end]
            core_offset = left_overlap
            core_count = end - start
            logging.info(
                "[auto_edit] chunk %d core=[%d,%d] core_count=%d context=[%d,%d] context_count=%d",
                chunk_index,
                start + 1,
                end,
                core_count,
                context_start + 1,
                context_end,
                len(seg_chunk),
            )
            try:
                chunk_result = self._auto_edit_segment_chunk(seg_chunk)
            except Exception as exc:
                raise RuntimeError(
                    f"Auto-edit chunk failed at lines [{start + 1}, {end}]: {exc}"
                ) from exc

            core_optimized_subs = chunk_result["optimized_subs"][core_offset : core_offset + core_count]
            core_segments = seg_chunk[core_offset : core_offset + core_count]
            if len(core_optimized_subs) != core_count or len(core_segments) != core_count:
                raise RuntimeError(
                    f"Chunk core slice mismatch at lines [{start + 1}, {end}]."
                )

            optimized_subs_all.extend(core_optimized_subs)
            for seg, sub in zip(core_segments, core_optimized_subs):
                # 暂不过滤，保留所有行用于后续合并
                kept_segments_all.append(
                    {
                        "start": float(seg.get("start") or 0.0),
                        "end": float(seg.get("end") or 0.0),
                        "content": sub.content,  # 保存内容用于合并判断
                    }
                )
            chunk_debug.append(
                {
                    "chunk_index": chunk_index,
                    "line_start": start + 1,
                    "line_end": end,
                    "line_count": core_count,
                    "context_line_start": context_start + 1,
                    "context_line_end": context_end,
                    "context_line_count": len(seg_chunk),
                    "context_left_overlap": left_overlap,
                    "context_right_overlap": right_overlap,
                    "debug": chunk_result["debug"],
                }
            )

        if not kept_segments_all:
            raise RuntimeError("All segments removed. Check LLM output.")

        # Step 3: 合并短句（在所有 chunk 处理完成后）
        merged_subs, merged_segments = self._merge_short_lines_in_subs(
            optimized_subs_all,
            [{"start": s["start"], "end": s["end"]} for s in kept_segments_all]
        )

        edl = _segments_to_edl(merged_segments, self.cfg, total_length)
        return {
            "optimized_subs": merged_subs,
            "edl": edl,
            "debug": {
                "chunked": True,
                "chunk_size": AUTO_EDIT_CHUNK_LINES,
                "chunk_overlap_lines": AUTO_EDIT_CHUNK_OVERLAP_LINES,
                "chunk_count": len(chunk_debug),
                "chunks": chunk_debug,
            },
        }

    def _auto_edit_segment_chunk(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        tagged_text = _segments_to_tagged_text(segments)

        # Step 1: full-text semantic remove pass.
        remove_messages = _build_llm_remove_prompt(tagged_text)
        remove_text = llm_utils.chat_completion(self.llm_config, remove_messages)
        remove_text = _strip_code_fence(remove_text).strip()
        if not remove_text:
            raise RuntimeError("LLM returned empty remove-pass text.")

        remove_mapped, remove_missing, remove_duplicates, remove_cleaned = _parse_tagged_output(
            remove_text, segments
        )
        if remove_missing:
            logging.warning(
                "LLM remove pass missing %d line tags; fallback to KEEP for missing lines. "
                "Re-run if this keeps happening.",
                len(remove_missing),
            )
            for idx in remove_missing:
                remove_mapped[idx] = (segments[idx - 1].get("text") or "").strip()
        if remove_duplicates:
            logging.warning(
                "LLM remove pass has duplicated line tags: "
                f"{sorted(set(remove_duplicates))[:8]}"
            )

        remove_flags: List[bool] = []
        remove_stage_lines: List[str] = []
        for idx, seg in enumerate(segments, start=1):
            raw_text = (remove_mapped.get(idx) or "").strip()
            orig_text = (seg.get("text") or "").strip()
            # No-speech placeholders are always removed by deterministic rule.
            remove = _is_no_speech_text(orig_text) or _is_remove_line(raw_text)
            remove_flags.append(remove)
            if remove:
                remove_stage_lines.append(f"[L{idx:04d}] {REMOVE_TOKEN}")
            else:
                # Keep original text for step 2 to ensure remove/optimize responsibilities are split.
                remove_stage_lines.append(f"[L{idx:04d}] {orig_text}")
        remove_stage_text = "\n".join(remove_stage_lines)

        # Step 2: optimize wording for kept lines only.
        optimize_messages = _build_llm_optimize_prompt(remove_stage_text)
        optimize_text = llm_utils.chat_completion(self.llm_config, optimize_messages)
        optimize_text = _strip_code_fence(optimize_text).strip()
        if not optimize_text:
            raise RuntimeError("LLM returned empty optimize-pass text.")

        optimize_mapped, optimize_missing, optimize_duplicates, optimize_cleaned = _parse_tagged_output(
            optimize_text, segments
        )
        if optimize_missing:
            logging.warning(
                "LLM optimize pass missing %d line tags; fallback to original ASR text "
                "for missing lines. Re-run if this keeps happening.",
                len(optimize_missing),
            )
            for idx in optimize_missing:
                # 缺失行直接使用原始 ASR 文本（不标记为删除）
                optimize_mapped[idx] = (segments[idx - 1].get("text") or "").strip()
        if optimize_duplicates:
            logging.warning(
                "LLM optimize pass has duplicated line tags: "
                f"{sorted(set(optimize_duplicates))[:8]}"
            )

        optimized_subs: List[srt.Subtitle] = []
        kept_segments: List[Dict[str, Any]] = []
        for idx, seg in enumerate(segments, start=1):
            raw_text = (optimize_mapped.get(idx) or "").strip()
            orig_text = (seg.get("text") or "").strip()
            remove = remove_flags[idx - 1]

            if remove:
                if not _is_remove_line(raw_text):
                    logging.warning(
                        "LLM optimize pass attempted to restore removed line [L%04d]; keeping remove.",
                        idx,
                    )
                if orig_text:
                    new_text = f"{REMOVE_TOKEN} {orig_text}".strip()
                else:
                    new_text = REMOVE_TOKEN
            else:
                if _is_remove_line(raw_text):
                    logging.warning(
                        "LLM optimize pass attempted to remove kept line [L%04d]; using original text.",
                        idx,
                    )
                    new_text = _normalize_line_text(orig_text)
                else:
                    new_text = _normalize_line_text(raw_text or orig_text)

            sub = srt.Subtitle(
                index=int(seg.get("id") or idx),
                start=datetime.timedelta(seconds=float(seg.get("start") or 0.0)),
                end=datetime.timedelta(seconds=float(seg.get("end") or 0.0)),
                content=new_text,
            )
            optimized_subs.append(sub)

            if not remove:
                kept_segments.append(
                    {
                        "start": float(seg.get("start") or 0.0),
                        "end": float(seg.get("end") or 0.0),
                    }
                )

        return {
            "optimized_subs": optimized_subs,
            "kept_segments": kept_segments,
            "debug": {
                "edited_text": optimize_text,
                "remove_token": REMOVE_TOKEN,
                "raw_output": optimize_cleaned,
                "missing_tags": optimize_missing,
                "duplicate_tags": optimize_duplicates,
                "remove_pass": {
                    "raw_output": remove_cleaned,
                    "missing_tags": remove_missing,
                    "duplicate_tags": remove_duplicates,
                },
                "optimize_pass": {
                    "raw_output": optimize_cleaned,
                    "missing_tags": optimize_missing,
                    "duplicate_tags": optimize_duplicates,
                },
            },
        }

    def _merge_short_lines_in_subs(
        self,
        subs: List[srt.Subtitle],
        segments: List[Dict[str, Any]],
        threshold: int = MERGE_SHORT_LINES_THRESHOLD,
    ) -> Tuple[List[srt.Subtitle], List[Dict[str, Any]]]:
        """
        在删除+润色完成后，合并短句字幕。
        
        规则：
        1. 保留标记为 <<REMOVE>> 的行（不删除）
        2. <<REMOVE>> 行不参与合并，并且阻断前后合并
        3. 如果当前行字数 < threshold，持续与后续行合并，直到：
           - 合并后的字数 >= threshold，或
           - 没有更多行可合并
        4. 如果当前行字数 >= threshold，直接保留（不向后合并）
        5. 合并时：文字用逗号连接，时间戳取合并范围的最小start和最大end
        
        返回：
        - 合并后的 subtitles（包含 remove 行，便于 Step UI 保留删除标记）
        - 仅保留有效内容的 segments（不含 remove 行，用于 EDL）
        """
        if not subs:
            return [], []

        merged_subs: List[srt.Subtitle] = []
        merged_segments: List[Dict[str, Any]] = []

        n = min(len(subs), len(segments))
        i = 0
        while i < n:
            current_sub = subs[i]
            current_seg = segments[i]
            current_text = (current_sub.content or "").strip()

            if _is_remove_line(current_text):
                # Keep remove markers in Step output and treat them as hard merge boundaries.
                merged_subs.append(
                    srt.Subtitle(
                        index=int(current_sub.index),
                        start=current_sub.start,
                        end=current_sub.end,
                        content=current_text,
                    )
                )
                i += 1
                continue

            if len(current_text) >= threshold:
                merged_subs.append(
                    srt.Subtitle(
                        index=int(current_sub.index),
                        start=current_sub.start,
                        end=current_sub.end,
                        content=current_text,
                    )
                )
                merged_segments.append(
                    {
                        "start": float(current_seg.get("start") or 0.0),
                        "end": float(current_seg.get("end") or 0.0),
                    }
                )
                i += 1
                continue

            merged_text = current_text
            merged_start = float(current_seg.get("start") or 0.0)
            merged_end = float(current_seg.get("end") or 0.0)
            j = i + 1

            while j < n:
                next_sub = subs[j]
                next_text = (next_sub.content or "").strip()
                if _is_remove_line(next_text):
                    break
                next_seg = segments[j]
                merged_text = _smart_join_text(merged_text, next_text)
                merged_start = min(merged_start, float(next_seg.get("start") or 0.0))
                merged_end = max(merged_end, float(next_seg.get("end") or 0.0))
                j += 1
                if len(merged_text) >= threshold:
                    break

            merged_subs.append(
                srt.Subtitle(
                    index=int(current_sub.index),
                    start=datetime.timedelta(seconds=merged_start),
                    end=datetime.timedelta(seconds=merged_end),
                    content=merged_text,
                )
            )
            merged_segments.append(
                {
                    "start": merged_start,
                    "end": merged_end,
                }
            )
            i = j

        # Preserve any trailing remove-only lines when input lengths mismatch unexpectedly.
        for tail_idx in range(n, len(subs)):
            tail_sub = subs[tail_idx]
            tail_text = (tail_sub.content or "").strip()
            if _is_remove_line(tail_text):
                merged_subs.append(
                    srt.Subtitle(
                        index=int(tail_sub.index),
                        start=tail_sub.start,
                        end=tail_sub.end,
                        content=tail_text,
                    )
                )

        return merged_subs, merged_segments

    def _resolve_topic_output(self, optimized_srt: str) -> Optional[str]:
        output = getattr(self.args, "topic_output", None)
        if not output:
            return None
        if len(self.args.inputs) > 1:
            logging.warning(
                "--topic-output ignored in auto-edit because multiple input files were provided."
            )
            return None
        return output


def _maybe_skip(path: str, force: bool) -> bool:
    if os.path.exists(path):
        if force:
            logging.info(f"{path} exists. Will overwrite it")
            return False
        logging.info(f"{path} exists, skipping... Use --force to overwrite")
        return True
    return False
