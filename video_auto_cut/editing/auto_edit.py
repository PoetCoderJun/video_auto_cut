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
NO_SPEECH_PATTERN = re.compile(r"^\s*<\s*no\s*speech\s*>\s*$", re.IGNORECASE)
TIME_PREFIX_PATTERN = re.compile(r"^\[\d{1,3}:\d{2}\]\s*")
AUTO_EDIT_CHUNK_LINES = 50


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
        "你是口播文案删减助手。输入是完整asr转写文案，每行对应一个字幕句子。"
        "场景：口播常先说错，后面会纠正，这时候字幕上反映出来就是重复说了很多语义。"
        "任务：只判断每行是否删除，不做改写。"
        "规则：对相同或相似语义（含连续错误尝试），只保留最后一个完整且正确的表达，前面的重复/试错内容一并删除。"
        f"删除行输出 {REMOVE_TOKEN}。保留行必须原样回填，不允许改字、改词、改标点。"
        "禁止跨行操作：不要合并/拆分/重排句子。"
        "必须保留每一行的行号标签，且行数必须与输入完全一致。"
        "仅输出删减后的完整文案，不要输出任何解释。"
    )
    user = f"原文：\n{tagged_text}\n\n请输出第一步删减结果："
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_llm_optimize_prompt(tagged_text: str) -> List[Dict[str, str]]:
    system = (
        "你是口播视频的文案优化助手。输入是第一步删减结果，每行对应一个字幕句子。"
        "第二步任务：只优化句子、用词和标点，降低 ASR 错误并提升可读性。"
        "重点修正明显 ASR 错误（同音字、冗余的语气词、错词）并恢复标点。"
        "请去除无实际语义的口头语/语气词，如“嗯、啊、哦、呃”等（不改变句意）。"
        "不要新增或删减语义，不要改写句意。"
        "每行文本长度应尽量接近原句。"
        f"对于标记为 {REMOVE_TOKEN} 的行，必须原样输出 {REMOVE_TOKEN}，保留{REMOVE_TOKEN} 但是对后面的内容也进行修正明显 ASR 错误。"
        "禁止新增删除，不要把保留行改成删除。"
        "禁止跨行操作：不要合并/拆分/重排句子。"
        "必须保留每一行的行号标签，且行数必须与输入完全一致。"
        "仅输出优化后的完整文案，不要输出任何解释。"
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
        if len(segments) <= AUTO_EDIT_CHUNK_LINES:
            chunk_result = self._auto_edit_segment_chunk(segments)
            if not chunk_result["kept_segments"]:
                raise RuntimeError("All segments removed. Check LLM output.")
            edl = _segments_to_edl(chunk_result["kept_segments"], self.cfg, total_length)
            return {
                "optimized_subs": chunk_result["optimized_subs"],
                "edl": edl,
                "debug": chunk_result["debug"],
            }

        logging.info(
            "[auto_edit] segment count=%d exceeds chunk limit=%d, processing in chunks",
            len(segments),
            AUTO_EDIT_CHUNK_LINES,
        )
        optimized_subs_all: List[srt.Subtitle] = []
        kept_segments_all: List[Dict[str, Any]] = []
        chunk_debug: List[Dict[str, Any]] = []

        for chunk_index, start in enumerate(range(0, len(segments), AUTO_EDIT_CHUNK_LINES), start=1):
            end = min(start + AUTO_EDIT_CHUNK_LINES, len(segments))
            seg_chunk = segments[start:end]
            logging.info(
                "[auto_edit] chunk %d line_range=[%d,%d] line_count=%d",
                chunk_index,
                start + 1,
                end,
                len(seg_chunk),
            )
            try:
                chunk_result = self._auto_edit_segment_chunk(seg_chunk)
            except Exception as exc:
                raise RuntimeError(
                    f"Auto-edit chunk failed at lines [{start + 1}, {end}]: {exc}"
                ) from exc

            optimized_subs_all.extend(chunk_result["optimized_subs"])
            kept_segments_all.extend(chunk_result["kept_segments"])
            chunk_debug.append(
                {
                    "chunk_index": chunk_index,
                    "line_start": start + 1,
                    "line_end": end,
                    "line_count": len(seg_chunk),
                    "debug": chunk_result["debug"],
                }
            )

        if not kept_segments_all:
            raise RuntimeError("All segments removed. Check LLM output.")

        edl = _segments_to_edl(kept_segments_all, self.cfg, total_length)
        return {
            "optimized_subs": optimized_subs_all,
            "edl": edl,
            "debug": {
                "chunked": True,
                "chunk_size": AUTO_EDIT_CHUNK_LINES,
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
                "Consider increasing --llm-max-tokens.",
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
                "LLM optimize pass missing %d line tags; fallback to remove-pass/original text "
                "for missing lines. Consider increasing --llm-max-tokens.",
                len(optimize_missing),
            )
            for idx in optimize_missing:
                if remove_flags[idx - 1]:
                    optimize_mapped[idx] = REMOVE_TOKEN
                else:
                    optimize_mapped[idx] = (segments[idx - 1].get("text") or "").strip()
        if optimize_duplicates:
            logging.warning(
                "LLM optimize pass has duplicated line tags: "
                f"{sorted(set(optimize_duplicates))[:8]}"
            )

        optimized_subs: List[srt.Subtitle] = []
        kept_segments: List[Dict[str, Any]] = []
        restored_removed_lines: List[int] = []
        for idx, seg in enumerate(segments, start=1):
            raw_text = (optimize_mapped.get(idx) or "").strip()
            orig_text = (seg.get("text") or "").strip()
            remove = remove_flags[idx - 1]

            if remove:
                # Line-level recovery only: if optimize pass produced non-remove content
                # for a line removed by remove pass, restore this line instead of keeping it removed.
                if not _is_remove_line(raw_text):
                    restored_removed_lines.append(idx)
                    new_text = raw_text or orig_text
                    remove = False
                    logging.warning(
                        "Recovered removed line [L%04d] because optimize pass returned content.",
                        idx,
                    )
                else:
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
                    new_text = orig_text
                else:
                    new_text = raw_text or orig_text

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
                "restored_removed_lines": restored_removed_lines,
            },
        }

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
