import datetime
import json
import logging
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import srt

from . import llm_utils


REMOVE_TOKEN = "<<REMOVE>>"
TAG_PATTERN = re.compile(r"^\[L(\d{1,6})\]\s*(.*)$")


@dataclass
class AutoEditConfig:
    merge_gap_s: float = 0.5
    pad_head_s: float = 0.0
    pad_tail_s: float = 0.0


def _segments_to_tagged_text(segments: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        text = (seg.get("text") or "").strip()
        lines.append(f"[L{idx:04d}] {text}")
    return "\n".join(lines)


def _build_llm_edit_prompt(tagged_text: str) -> List[Dict[str, str]]:
    system = (
        "你是口播视频的文案优化助手。输入是完整转写文案（已纠错），每行对应一个字幕句子。"
        "你的任务：基于全文语义删除水词/水段和语义重复内容，并在每行内修正用词与语病。"
        "如果一个语义被多次表达，通常后面的是纠正，前面必须标记为删除，后面的保留。"
        "允许在单行内改字、改词、补标点，但禁止跨行修改：不要合并/拆分/重排句子。"
        f"如果要删除某行，请保留行号并输出 {REMOVE_TOKEN}。"
        "必须保留每一行的行号标签，且行数必须与输入完全一致。"
        "仅输出优化后的完整文案，不要输出任何解释。"
    )
    user = f"原文：\n{tagged_text}\n\n请输出优化后的完整文案："
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
            temperature=self.args.llm_temperature,
            max_tokens=self.args.llm_max_tokens,
        )
        if not self.llm_config.get("base_url") or not self.llm_config.get("model"):
            raise RuntimeError(
                "LLM config missing. Set --llm-base-url and --llm-model to use auto-edit LLM."
            )

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

    def _auto_edit_segments(
        self, segments: List[Dict[str, Any]], total_length: Optional[float]
    ) -> Dict[str, Any]:
        tagged_text = _segments_to_tagged_text(segments)
        edit_messages = _build_llm_edit_prompt(tagged_text)
        edited_text = llm_utils.chat_completion(self.llm_config, edit_messages)
        edited_text = _strip_code_fence(edited_text).strip()
        if not edited_text:
            raise RuntimeError("LLM returned empty edited text.")

        mapped, missing, duplicates, cleaned = _parse_tagged_output(edited_text, segments)
        if missing:
            raise RuntimeError(
                f"LLM output missing {len(missing)} line tags. "
                "Please re-run or increase --llm-max-tokens."
            )
        if duplicates:
            logging.warning(f"LLM output has duplicated line tags: {sorted(set(duplicates))[:8]}")

        optimized_subs: List[srt.Subtitle] = []
        kept_segments: List[Dict[str, Any]] = []
        for idx, seg in enumerate(segments, start=1):
            raw_text = (mapped.get(idx) or "").strip()
            orig_text = (seg.get("text") or "").strip()
            remove = False
            if not raw_text:
                remove = True
            elif raw_text == REMOVE_TOKEN:
                remove = True
            elif raw_text.startswith(REMOVE_TOKEN):
                remove = True

            if remove:
                if orig_text:
                    new_text = f"{REMOVE_TOKEN} {orig_text}".strip()
                else:
                    new_text = REMOVE_TOKEN
            else:
                new_text = raw_text

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

        if not kept_segments:
            raise RuntimeError("All segments removed. Check LLM output.")

        edl = _segments_to_edl(kept_segments, self.cfg, total_length)
        return {
            "optimized_subs": optimized_subs,
            "edl": edl,
            "debug": {
                "edited_text": edited_text,
                "remove_token": REMOVE_TOKEN,
                "raw_output": cleaned,
                "missing_tags": missing,
                "duplicate_tags": duplicates,
            },
        }


def _maybe_skip(path: str, force: bool) -> bool:
    if os.path.exists(path):
        if force:
            logging.info(f"{path} exists. Will overwrite it")
            return False
        logging.info(f"{path} exists, skipping... Use --force to overwrite")
        return True
    return False
