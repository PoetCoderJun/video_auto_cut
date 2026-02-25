from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .filetrans_like import (
    FiletransResult,
    FiletransSegment,
    FiletransSubmitResponse,
    FiletransTask,
)


@dataclass(frozen=True)
class DashScopeFiletransConfig:
    base_url: str
    api_key: str
    model: str
    task: str | None
    poll_seconds: float
    timeout_seconds: float
    language_hints: tuple[str, ...]
    context: str
    enable_words: bool
    word_split_enabled: bool
    word_split_on_comma: bool
    word_split_comma_pause_s: float
    word_split_min_chars: int
    word_vad_gap_s: float
    word_max_segment_s: float


class DashScopeFiletransClient:
    def __init__(self, config: DashScopeFiletransConfig) -> None:
        self._config = config
        if not self._config.api_key:
            raise RuntimeError("DashScope API key missing for ASR.")

    @property
    def poll_seconds(self) -> float:
        return self._config.poll_seconds

    @property
    def timeout_seconds(self) -> float:
        return self._config.timeout_seconds

    def submit(self, *, file_url: str, lang: str | None, prompt: str) -> FiletransSubmitResponse:
        language_hints = self._build_language_hints(lang)
        context = (prompt or self._config.context or "").strip()
        payload = self._build_submit_payload(
            file_url=file_url,
            language_hints=language_hints,
            context=context,
            use_file_urls=False,
        )
        try:
            data = self._post_json(
                "/api/v1/services/audio/asr/transcription",
                payload,
            )
        except RuntimeError as exc:
            text = str(exc)
            # Compatibility fallback for API variants expecting input.file_urls.
            if "InvalidParameter" not in text or "url" not in text.lower():
                raise
            fallback_payload = self._build_submit_payload(
                file_url=file_url,
                language_hints=language_hints,
                context=context,
                use_file_urls=True,
            )
            data = self._post_json(
                "/api/v1/services/audio/asr/transcription",
                fallback_payload,
            )
        output = data.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"Unexpected submit response from DashScope: {data}")
        task_id = str(output.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError(f"Missing task_id in DashScope response: {data}")
        return FiletransSubmitResponse(task_id=task_id)

    def _build_submit_payload(
        self,
        *,
        file_url: str,
        language_hints: list[str],
        context: str,
        use_file_urls: bool,
    ) -> dict[str, Any]:
        input_payload: dict[str, Any]
        if use_file_urls:
            input_payload = {"file_urls": [file_url]}
        else:
            input_payload = {"file_url": file_url}

        payload: dict[str, Any] = {
            "model": self._config.model,
            "input": input_payload,
            "parameters": {},
        }
        task = (self._config.task or "").strip()
        if task:
            payload["task"] = task
        if language_hints:
            payload["parameters"]["language_hints"] = language_hints
        if context:
            payload["parameters"]["context"] = context
        payload["parameters"]["enable_words"] = bool(self._config.enable_words)
        if not payload["parameters"]:
            payload.pop("parameters")
        return payload

    def poll(self, task_id: str) -> FiletransTask:
        data = self._get_json(f"/api/v1/tasks/{task_id}")
        output = data.get("output")
        if not isinstance(output, dict):
            return FiletransTask(task_id=task_id, task_status="RUNNING")

        status = str(output.get("task_status") or "").strip().upper() or "RUNNING"
        task_status = _normalize_status(status)
        transcription_url = _extract_transcription_url(output)
        error_message = (
            str(output.get("message") or data.get("message") or "").strip() or None
        )
        return FiletransTask(
            task_id=task_id,
            task_status=task_status,
            transcription_url=transcription_url,
            error_message=error_message,
        )

    def load_result(self, transcription_url: str) -> FiletransResult:
        payload = self._open_json_url(transcription_url, headers={})
        segments = self._parse_segments(payload)
        return FiletransResult(task_id="", segments=segments)

    def _parse_segments(self, payload: dict[str, Any]) -> list[FiletransSegment]:
        segments: list[FiletransSegment] = []
        seen = set()
        for row in _candidate_rows(payload):
            row_segments = self._segments_from_row(row)
            for seg in row_segments:
                key = (round(seg.start, 3), round(seg.end, 3), seg.text)
                if key in seen:
                    continue
                seen.add(key)
                segments.append(seg)
        segments.sort(key=lambda item: (item.start, item.end))
        return self._cleanup_segments(segments)

    def _segments_from_row(self, row: dict[str, Any]) -> list[FiletransSegment]:
        words = row.get("words")
        if (
            bool(self._config.enable_words)
            and bool(self._config.word_split_enabled)
            and isinstance(words, list)
            and words
        ):
            split_segments = self._split_by_words(words)
            if split_segments:
                return split_segments

        text = _first_text(row)
        if not text:
            return []
        start = _read_time_s(row, ("begin_time", "sentence_begin_time", "start_time"), ms=True)
        end = _read_time_s(row, ("end_time", "sentence_end_time", "stop_time"), ms=True)
        if start is None:
            start = _read_time_s(row, ("start_ms",), ms=True)
        if end is None:
            end = _read_time_s(row, ("end_ms",), ms=True)
        if start is None:
            start = _read_time_s(row, ("start", "begin"), ms=False)
        if end is None:
            end = _read_time_s(row, ("end", "stop"), ms=False)
        if start is None or end is None or end <= start:
            return []
        return [FiletransSegment(start=float(start), end=float(end), text=text)]

    def _split_by_words(self, words: list[dict[str, Any]]) -> list[FiletransSegment]:
        normalized: list[dict[str, Any]] = []
        for item in words:
            if not isinstance(item, dict):
                continue
            try:
                begin = float(item.get("begin_time"))
                end = float(item.get("end_time"))
            except Exception:
                continue
            text = str(item.get("text") or "")
            punctuation = str(item.get("punctuation") or "")
            if end <= begin:
                continue
            if not text and not punctuation:
                continue
            normalized.append(
                {
                    "begin": begin,
                    "end": end,
                    "text": text,
                    "punct": punctuation,
                }
            )
        if not normalized:
            return []

        strong_punc = {"。", "！", "？", "!", "?", "；", ";"}
        comma_punc = {"，", ",", "、"}
        min_chars = max(1, int(self._config.word_split_min_chars))
        vad_gap_ms = max(0.0, float(self._config.word_vad_gap_s) * 1000.0)
        comma_pause_ms = max(0.0, float(self._config.word_split_comma_pause_s) * 1000.0)
        max_seg_ms = max(1000.0, float(self._config.word_max_segment_s) * 1000.0)

        out: list[FiletransSegment] = []
        current: list[dict[str, Any]] = []

        def _flush() -> None:
            if not current:
                return
            start_ms = current[0]["begin"]
            end_ms = current[-1]["end"]
            if end_ms <= start_ms:
                current.clear()
                return
            text = "".join(f"{item['text']}{item['punct']}" for item in current).strip()
            current.clear()
            if not text:
                return
            out.append(
                FiletransSegment(
                    start=float(start_ms) / 1000.0,
                    end=float(end_ms) / 1000.0,
                    text=text,
                )
            )

        for idx, item in enumerate(normalized):
            current.append(item)

            seg_chars = sum(len(str(x["text"])) + len(str(x["punct"])) for x in current)
            seg_ms = current[-1]["end"] - current[0]["begin"]
            punct = str(item["punct"] or "")
            next_item = normalized[idx + 1] if idx + 1 < len(normalized) else None
            gap_ms = (
                float(next_item["begin"] - item["end"]) if next_item is not None else 0.0
            )

            split = False
            if punct in strong_punc:
                split = True
            elif (
                bool(self._config.word_split_on_comma)
                and punct in comma_punc
                and seg_chars >= min_chars
                and gap_ms >= comma_pause_ms
            ):
                split = True
            elif gap_ms >= vad_gap_ms and seg_chars >= min_chars:
                split = True
            elif seg_ms >= max_seg_ms and punct in strong_punc:
                split = True

            if split:
                _flush()

        _flush()
        return out

    @staticmethod
    def _cleanup_segments(segments: list[FiletransSegment]) -> list[FiletransSegment]:
        if not segments:
            return []

        # 1) Drop tiny overlap artifacts like "甚。" that duplicate next sentence prefix.
        pruned: list[FiletransSegment] = []
        for idx, seg in enumerate(segments):
            text = (seg.text or "").strip()
            duration = float(seg.end - seg.start)
            if idx + 1 < len(segments):
                next_text = (segments[idx + 1].text or "").strip()
            else:
                next_text = ""
            plain = text.rstrip("，。！？!?；;、")
            if (
                len(plain) <= 2
                and duration <= 0.6
                and plain
                and next_text.startswith(plain)
            ):
                continue
            pruned.append(seg)

        # 2) Make timeline monotonic and remove near-empty fragments.
        normalized: list[FiletransSegment] = []
        for seg in pruned:
            start = float(seg.start)
            end = float(seg.end)
            text = (seg.text or "").strip()
            if not text:
                continue
            if normalized and start < normalized[-1].end:
                # Keep continuity but avoid backwards overlap.
                start = float(normalized[-1].end)
            if end <= start + 0.05:
                continue
            normalized.append(FiletransSegment(start=start, end=end, text=text))
        return normalized

    def _build_language_hints(self, lang: str | None) -> list[str]:
        hints = [item for item in self._config.language_hints if item]
        raw_lang = (lang or "").strip()
        if raw_lang:
            mapped = _map_lang_hint(raw_lang)
            if mapped and mapped not in hints:
                hints.insert(0, mapped)
        return hints

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
            "X-DashScope-Async": "enable",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=self._resolve(path),
            data=body,
            headers=self._headers(extra_headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_error_text(exc)
            raise RuntimeError(f"DashScope submit failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope submit failed: {exc}") from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url=self._resolve(path),
            headers=self._headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_error_text(exc)
            raise RuntimeError(f"DashScope poll failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope poll failed: {exc}") from exc

    def _open_json_url(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        req = urllib.request.Request(url=url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_error_text(exc)
            raise RuntimeError(
                f"DashScope transcription result fetch failed: HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope transcription result fetch failed: {exc}") from exc

    def _resolve(self, path: str) -> str:
        base = self._config.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path


def _read_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        body = ""
    return body.strip() or exc.reason or "unknown error"


def _normalize_status(status: str) -> str:
    if status == "SUCCEEDED":
        return "SUCCEEDED"
    if status in {"FAILED", "CANCELED", "CANCELLED"}:
        return "FAILED"
    return "RUNNING"


def _extract_transcription_url(output: dict[str, Any]) -> str | None:
    direct = output.get("transcription_url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    result = output.get("result")
    if isinstance(result, dict):
        nested = result.get("transcription_url")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    results = output.get("results")
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        value = item.get("transcription_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    sentences = payload.get("sentences")
    if isinstance(sentences, list):
        rows.extend(item for item in sentences if isinstance(item, dict))

    transcripts = payload.get("transcripts")
    if isinstance(transcripts, list):
        for tr in transcripts:
            if not isinstance(tr, dict):
                continue
            tr_sentences = tr.get("sentences")
            if isinstance(tr_sentences, list):
                rows.extend(item for item in tr_sentences if isinstance(item, dict))
            else:
                rows.append(tr)

    raw_segments = payload.get("segments")
    if isinstance(raw_segments, list):
        rows.extend(item for item in raw_segments if isinstance(item, dict))

    return rows


def _first_text(row: dict[str, Any]) -> str:
    for key in ("text", "transcript", "content"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_time_s(row: dict[str, Any], keys: tuple[str, ...], *, ms: bool) -> float | None:
    for key in keys:
        if key not in row:
            continue
        raw = row.get(key)
        try:
            value = float(raw)
        except Exception:
            continue
        if ms:
            return value / 1000.0
        return value
    return None


def _map_lang_hint(lang: str) -> str:
    lowered = lang.strip().lower()
    mapping = {
        "chinese": "zh",
        "zh": "zh",
        "zh-cn": "zh",
        "mandarin": "zh",
        "english": "en",
        "en": "en",
        "en-us": "en",
        "cantonese": "yue",
        "yue": "yue",
    }
    return mapping.get(lowered, "")
