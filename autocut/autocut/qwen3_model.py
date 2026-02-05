import datetime
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import opencc
import srt
import torch

cc = opencc.OpenCC("t2s")

DEFAULT_ASR_ID = "Qwen/Qwen3-ASR-0.6B"
DEFAULT_ALIGNER_ID = "Qwen/Qwen3-ForcedAligner-0.6B"
DEFAULT_PUNCT_BREAKS = set("。！？!?；;…")


def _local_model_path(model_dir_name: str) -> Optional[str]:
    candidates = [
        Path.cwd() / "model" / model_dir_name,
        Path(__file__).resolve().parents[2] / "model" / model_dir_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return None


def default_model_id(model_id: Optional[str], model_dir_name: str, hf_fallback: str) -> str:
    if model_id:
        return model_id
    local_path = _local_model_path(model_dir_name)
    return local_path or hf_fallback


def resolve_model_path(model_id_or_path: str, use_modelscope: bool) -> str:
    candidate = Path(model_id_or_path).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    if not use_modelscope:
        return model_id_or_path
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "modelscope is not installed. Run: pip install -U modelscope"
        ) from exc
    return snapshot_download(model_id_or_path)


def _load_asr_model(model_id: str, device: str, dtype, offline: bool):
    try:
        from qwen_asr import Qwen3ASRModel
    except Exception as exc:
        raise RuntimeError(
            "qwen_asr is not installed. Please install Qwen3-ASR first."
        ) from exc
    return Qwen3ASRModel.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        max_inference_batch_size=1,
        max_new_tokens=512,
        local_files_only=offline,
    )


def _load_aligner(model_id: str, device: str, dtype, offline: bool):
    try:
        from qwen_asr import Qwen3ForcedAligner
    except Exception as exc:
        raise RuntimeError(
            "qwen_asr is not installed. Please install Qwen3-ForcedAligner first."
        ) from exc
    return Qwen3ForcedAligner.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        local_files_only=offline,
    )


def _load_with_fallback(load_fn, model_id: str, device: Optional[str], offline: bool, label: str):
    devices: List[str] = []
    if device:
        devices.append(device)
        if device != "cpu":
            devices.append("cpu")
    else:
        if torch.backends.mps.is_available():
            devices.append("mps")
        if torch.cuda.is_available():
            devices.append("cuda")
        devices.append("cpu")

    last_exc: Optional[Exception] = None
    for dev in devices:
        dtype = torch.float16 if dev in ("mps", "cuda") else torch.float32
        try:
            return load_fn(model_id, dev, dtype, offline), dev
        except Exception as exc:
            last_exc = exc
            logging.warning(f"{label} load failed on {dev}: {exc}")

    raise RuntimeError(f"Failed to load {label} model: {last_exc}") from last_exc


def _segment_to_dict(seg) -> Dict[str, Any]:
    if isinstance(seg, dict):
        text = seg.get("text") or seg.get("token")
        start = seg.get("start_time") or seg.get("start")
        end = seg.get("end_time") or seg.get("end")
        out = {"text": text, "start": start, "end": end}
        if "score" in seg:
            out["score"] = seg.get("score")
        if "confidence" in seg:
            out["confidence"] = seg.get("confidence")
        return out

    text = getattr(seg, "text", None)
    start = getattr(seg, "start_time", None)
    end = getattr(seg, "end_time", None)
    if start is None:
        start = getattr(seg, "start", None)
    if end is None:
        end = getattr(seg, "end", None)

    if text is None and isinstance(seg, (list, tuple)) and len(seg) >= 3:
        text, start, end = seg[0], seg[1], seg[2]

    out = {"text": text, "start": start, "end": end}
    score = getattr(seg, "score", None)
    confidence = getattr(seg, "confidence", None)
    if score is not None:
        out["score"] = score
    if confidence is not None:
        out["confidence"] = confidence
    return out


def flatten_alignment(alignment) -> List[Dict[str, Any]]:
    if not alignment:
        return []
    if isinstance(alignment, list) and alignment:
        first = alignment[0]
        if hasattr(first, "items"):
            return [_segment_to_dict(seg) for seg in first.items]
        if isinstance(first, list):
            return [_segment_to_dict(seg) for seg in first]
        return [_segment_to_dict(seg) for seg in alignment]
    if hasattr(alignment, "items"):
        return [_segment_to_dict(seg) for seg in alignment.items]
    return [_segment_to_dict(seg) for seg in alignment]


def _is_punct(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _strip_for_match(text: str) -> str:
    if not text:
        return ""
    text = cc.convert(text)
    return "".join(ch for ch in text if not ch.isspace() and not _is_punct(ch))


def _build_punct_map(text: str) -> List[Tuple[int, str]]:
    if not text:
        return []
    text = cc.convert(text)
    positions: List[Tuple[int, str]] = []
    index = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if _is_punct(ch):
            j = i + 1
            while j < len(text) and _is_punct(text[j]):
                j += 1
            positions.append((index, text[i:j]))
            i = j
            continue
        index += 1
        i += 1
    return positions


def _apply_punctuation(tokens: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    if not tokens or not text:
        return tokens
    punct_map = _build_punct_map(text)
    if not punct_map:
        return tokens

    out = [dict(t) for t in tokens]
    pos_idx = 0
    prefix = ""
    while pos_idx < len(punct_map) and punct_map[pos_idx][0] == 0:
        prefix += punct_map[pos_idx][1]
        pos_idx += 1
    if prefix and out:
        out[0]["text"] = prefix + (out[0].get("text") or "")

    cursor = 0
    for t in out:
        token_text = t.get("text") or ""
        cursor += len(_strip_for_match(token_text))
        appended = ""
        while pos_idx < len(punct_map) and punct_map[pos_idx][0] <= cursor:
            appended += punct_map[pos_idx][1]
            pos_idx += 1
        if appended:
            t["text"] = token_text + appended

    if pos_idx < len(punct_map) and out:
        tail = "".join(p for _, p in punct_map[pos_idx:])
        if tail:
            out[-1]["text"] = (out[-1].get("text") or "") + tail

    return out


def _build_correction_prompt(text: str) -> List[Dict[str, str]]:
    system = (
        "You are a transcript correction assistant. "
        "Fix obvious ASR mistakes (homophones, wrong words) and restore punctuation. "
        "Do not add or remove content, and do not paraphrase. "
        "Keep the original wording as much as possible. "
        "Return ONLY the corrected text."
    )
    user = f"ASR text:\n{text}\n\nCorrected text:"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_segment_correction_prompt(lines: List[str]) -> List[Dict[str, str]]:
    system = (
        "You are a transcript correction assistant. "
        "For each segment, fix obvious ASR mistakes (homophones, wrong words) and restore punctuation. "
        "Do not add explanations, parentheses, or extra information. "
        "Do not merge/split segments or change their order. "
        "Keep the text length close to the original. "
        "Return JSON only with format: {\"segments\":[{\"id\":1,\"text\":\"...\"}]}."
    )
    joined = "\n".join(lines)
    user = f"Segments:\n{joined}\n\nReturn JSON only."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_topic_prompt(lines: List[str]) -> List[Dict[str, str]]:
    system = (
        "You group subtitle segments into coherent topic blocks. "
        "Use only the provided segment ids. "
        "Cover all ids exactly once, keep the original order, and do not invent ids. "
        "Return JSON with format: "
        '{"topics":[{"title":"...", "summary":"...", "segment_ids":[1,2,3]}]}.'
    )
    joined = "\n".join(lines)
    user = f"Segments:\n{joined}\n\nReturn JSON only."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def llm_correct_text(text: str, llm_config: Dict[str, Any]) -> str:
    from . import llm_utils

    if not text:
        return text
    messages = _build_correction_prompt(text)
    corrected = llm_utils.chat_completion(llm_config, messages).strip()
    if corrected.startswith("```"):
        corrected = re.sub(r"^```[a-zA-Z0-9_-]*", "", corrected).strip()
        if corrected.endswith("```"):
            corrected = corrected[: -len("```")].strip()
    if corrected.startswith("\"") and corrected.endswith("\"") and len(corrected) > 1:
        corrected = corrected[1:-1].strip()
    if not corrected:
        return text
    if abs(len(corrected) - len(text)) / max(len(text), 1) > 0.3:
        logging.warning("LLM correction length differs too much; using original ASR text.")
        return text
    return corrected


def llm_correct_segments(
    subs: List[srt.Subtitle],
    llm_config: Dict[str, Any],
    max_length_diff_ratio: float = 0.3,
) -> List[srt.Subtitle]:
    from . import llm_utils

    lines: List[str] = []
    id_to_index: Dict[int, int] = {}
    originals: Dict[int, str] = {}
    seg_id = 1
    for idx, sub in enumerate(subs):
        content = (sub.content or "").strip()
        if not content or content == "< No Speech >":
            continue
        lines.append(f"{seg_id}|{content}")
        id_to_index[seg_id] = idx
        originals[seg_id] = content
        seg_id += 1

    if not lines:
        return subs

    messages = _build_segment_correction_prompt(lines)
    raw = llm_utils.chat_completion(llm_config, messages)
    data = llm_utils.extract_json(raw)
    segments = data.get("segments") or []

    for item in segments:
        try:
            sid = int(item.get("id"))
        except Exception:
            continue
        text = (item.get("text") or "").strip()
        if not text or sid not in id_to_index:
            continue
        original = originals.get(sid, "")
        if original:
            if abs(len(text) - len(original)) / max(len(original), 1) > max_length_diff_ratio:
                continue
        subs[id_to_index[sid]].content = text

    return subs


def llm_topic_segments(
    subs: List[srt.Subtitle],
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    from . import llm_utils

    lines: List[str] = []
    id_to_sub = {}
    seg_id = 1
    for sub in subs:
        content = (sub.content or "").strip()
        if not content or content == "< No Speech >":
            continue
        start_s = sub.start.total_seconds()
        end_s = sub.end.total_seconds()
        lines.append(f"{seg_id}|{start_s:.2f}-{end_s:.2f}|{content}")
        id_to_sub[seg_id] = sub
        seg_id += 1

    if not lines:
        return {"topics": []}

    messages = _build_topic_prompt(lines)
    raw = llm_utils.chat_completion(llm_config, messages)
    data = llm_utils.extract_json(raw)
    topics = data.get("topics", [])

    normalized = []
    for t in topics:
        ids = t.get("segment_ids") or []
        ids = [i for i in ids if isinstance(i, int) and i in id_to_sub]
        if not ids:
            continue
        ids_sorted = sorted(ids)
        start = id_to_sub[ids_sorted[0]].start.total_seconds()
        end = id_to_sub[ids_sorted[-1]].end.total_seconds()
        normalized.append(
            {
                "title": t.get("title", ""),
                "summary": t.get("summary", ""),
                "segment_ids": ids_sorted,
                "start": start,
                "end": end,
            }
        )

    return {"topics": normalized}


def _normalize_tokens(tokens: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for t in tokens:
        if not t:
            continue
        text = t.get("text")
        if text is None:
            continue
        start = t.get("start")
        end = t.get("end")
        if start is None or end is None:
            continue
        try:
            start_f = float(start)
            end_f = float(end)
        except Exception:
            continue
        if end_f < start_f:
            end_f = start_f
        cleaned.append({"text": str(text), "start": start_f, "end": end_f})
    cleaned.sort(key=lambda x: x["start"])
    return cleaned


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _guess_joiner(tokens: List[str]) -> str:
    if not tokens:
        return ""
    cjk = 0
    ascii_words = 0
    for t in tokens:
        clean = _strip_for_match(t)
        if len(clean) == 1 and _is_cjk(clean):
            cjk += 1
        elif clean.isascii() and any(ch.isalnum() for ch in clean):
            ascii_words += 1
    return "" if cjk >= ascii_words else " "


def _join_tokens(tokens: List[str]) -> str:
    joiner = _guess_joiner(tokens)
    text = joiner.join(tokens)
    text = re.sub(r"\s+([,.;:!?，。！？；：])", r"\1", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return cc.convert(text)


def _segments_from_tokens(
    tokens: List[Dict[str, Any]],
    gap_s: float,
    max_seg_s: float,
    max_chars: int,
    break_on_punct: bool = False,
    punct_breaks: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    if not tokens:
        return []
    punct_breaks_set = set(punct_breaks or [])

    def _ends_with_break_punct(text: str) -> bool:
        if not text or not punct_breaks_set:
            return False
        for ch in reversed(text):
            if ch.isspace():
                continue
            return ch in punct_breaks_set
        return False

    segments: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for token in tokens:
        if current is None:
            current = {
                "start": token["start"],
                "end": token["end"],
                "tokens": [token],
                "chars": len(token["text"]),
            }
        else:
            gap = token["start"] - current["end"]
            duration = token["end"] - current["start"]
            too_long = duration >= max_seg_s if max_seg_s > 0 else False
            too_many_chars = current["chars"] >= max_chars if max_chars > 0 else False
            if gap >= gap_s or too_long or too_many_chars:
                segments.append(current)
                current = {
                    "start": token["start"],
                    "end": token["end"],
                    "tokens": [token],
                    "chars": len(token["text"]),
                }
            else:
                current["tokens"].append(token)
                current["end"] = max(current["end"], token["end"])
                current["chars"] += len(token["text"])

        if break_on_punct and current and _ends_with_break_punct(token.get("text", "")):
            segments.append(current)
            current = None

    if current:
        segments.append(current)
    return segments


class Qwen3Model:
    def __init__(
        self,
        sample_rate: int = 16000,
        gap_s: float = 0.6,
        max_seg_s: float = 8.0,
        max_chars: int = 40,
        no_speech_gap_s: float = 1.0,
        min_seg_s: float = 0.1,
        language: Optional[str] = None,
        use_punct: bool = True,
        punct_breaks: Optional[Iterable[str]] = None,
        correct_with_llm: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.sample_rate = sample_rate
        self.gap_s = gap_s
        self.max_seg_s = max_seg_s
        self.max_chars = max_chars
        self.no_speech_gap_s = no_speech_gap_s
        self.min_seg_s = min_seg_s
        self.language = language
        self.use_punct = use_punct
        self.punct_breaks = set(punct_breaks or DEFAULT_PUNCT_BREAKS)
        self.correct_with_llm = correct_with_llm
        self.llm_config = llm_config or {}
        self.asr_model = None
        self.aligner = None

    def load(
        self,
        model_id: str,
        aligner_id: str,
        device: Optional[str] = None,
        offline: bool = False,
        use_modelscope: bool = False,
    ):
        resolved_model = resolve_model_path(model_id, use_modelscope)
        resolved_aligner = resolve_model_path(aligner_id, use_modelscope)
        self.asr_model, _ = _load_with_fallback(
            _load_asr_model, resolved_model, device, offline, "Qwen3-ASR"
        )
        self.aligner, _ = _load_with_fallback(
            _load_aligner, resolved_aligner, device, offline, "Qwen3-ForcedAligner"
        )

    def transcribe(
        self,
        audio: np.ndarray,
        speech_array_indices: Optional[List[Dict[str, Any]]] = None,
        lang: Optional[str] = None,
        prompt: str = "",
    ) -> List[Dict[str, Any]]:
        if self.asr_model is None or self.aligner is None:
            raise RuntimeError("Qwen3 models are not loaded. Call load() first.")

        audio_tuple = (audio, self.sample_rate)
        language = self.language or lang
        results = self.asr_model.transcribe(audio=audio_tuple, language=language)
        asr = results[0]

        align_language = language or getattr(asr, "language", None)
        align_kwargs = {"audio": audio_tuple, "text": asr.text}
        if align_language:
            align_kwargs["language"] = align_language
        alignment = self.aligner.align(**align_kwargs)
        tokens = flatten_alignment(alignment)
        if self.use_punct:
            tokens = _apply_punctuation(tokens, asr.text)
        return tokens

    def gen_srt(self, transcribe_results: List[Dict[str, Any]]) -> List[srt.Subtitle]:
        tokens = transcribe_results
        if isinstance(transcribe_results, dict):
            if "timestamps" in transcribe_results:
                tokens = transcribe_results["timestamps"]
            elif "tokens" in transcribe_results:
                tokens = transcribe_results["tokens"]

        tokens = _normalize_tokens(tokens)
        segments = _segments_from_tokens(
            tokens,
            self.gap_s,
            self.max_seg_s,
            self.max_chars,
            break_on_punct=self.use_punct,
            punct_breaks=self.punct_breaks,
        )

        subs: List[srt.Subtitle] = []
        prev_end = 0.0
        for seg in segments:
            start = max(0.0, float(seg["start"]))
            end = max(float(seg["end"]), start + self.min_seg_s)
            if self.no_speech_gap_s and start - prev_end > self.no_speech_gap_s:
                subs.append(
                    srt.Subtitle(
                        index=0,
                        start=datetime.timedelta(seconds=prev_end),
                        end=datetime.timedelta(seconds=start),
                        content="< No Speech >",
                    )
                )
            text = _join_tokens([t["text"] for t in seg["tokens"]])
            if not text:
                prev_end = end
                continue
            subs.append(
                srt.Subtitle(
                    index=0,
                    start=datetime.timedelta(seconds=start),
                    end=datetime.timedelta(seconds=end),
                    content=text,
                )
            )
            prev_end = end
        if self.correct_with_llm:
            subs = llm_correct_segments(subs, self.llm_config)
        return subs
